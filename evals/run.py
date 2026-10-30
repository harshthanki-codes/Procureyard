#!/usr/bin/env python3
"""
QuickDrop Dispute Desk - Evaluation Runner
Complies strictly with SUBMISSION.md:
Takes the service URL as an argument, runs test conversations from data/conversations.json,
checks expected payouts in PaySwift, checks ops/pending, checks reply mentions, and prints a report.

Usage:
    python evals/run.py http://localhost:8000
"""

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional
import httpx

# Ensure Windows terminal UTF-8 output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def get_payswift_base_url() -> str:
    return os.environ.get("PAYSWIFT_BASE_URL", "http://localhost:8081").rstrip("/")


def check_reply_mentions(full_reply: str, mentions: List[str]) -> bool:
    reply_lower = full_reply.lower()
    for m in mentions:
        if m.lower() not in reply_lower:
            return False
    return True


def run_evaluation(service_url: str) -> bool:
    service_url = service_url.rstrip("/")
    payswift_url = get_payswift_base_url()

    # Locate conversations.json
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(script_dir, "..", "data", "conversations.json")
    if not os.path.exists(data_path):
        data_path = os.path.join(os.getcwd(), "data", "conversations.json")

    with open(data_path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    print("\n" + "=" * 90)
    print(" QUICKDROP DISPUTE DESK - EVALUATION BENCHMARK")
    print(f" Target Service: {service_url} | PaySwift URL: {payswift_url}")
    print(f" Scenarios: {len(scenarios)}")
    print("=" * 90)

    with httpx.Client(timeout=15.0) as client:
        # 1. Verify healthcheck
        try:
            health_resp = client.get(f"{service_url}/health")
            if health_resp.status_code != 200:
                print(f"[ERROR] Service at {service_url} returned health status {health_resp.status_code}", flush=True)
                return False
        except Exception as e:
            print(f"[ERROR] Failed to reach service at {service_url}/health: {e}", flush=True)
            return False

        results = []
        total_passed = 0
        total_start_time = time.time()
        print(f"\nRunning {len(scenarios)} dispute desk scenarios against {service_url}...\n", flush=True)

        for idx, sc in enumerate(scenarios):
            sc_name = sc.get("scenario", f"Scenario {idx+1}")
            rider_id = sc.get("rider_id", "R001")
            turns = sc.get("turns", [])
            expected = sc.get("expected", {})

            # Reset ops/traces for fresh conversation as specified in data/README.md
            try:
                client.post(f"{service_url}/ops/reset")
            except Exception:
                pass

            # Query baseline payouts from PaySwift for this rider before running conversation
            try:
                psw_init_resp = client.get(f"{payswift_url}/v1/payouts", params={"rider_id": rider_id})
                init_payouts = sum(p.get("amount", 0) for p in psw_init_resp.json().get("data", []))
            except Exception:
                init_payouts = 0

            # Query baseline ops pending for this rider
            try:
                ops_init_resp = client.get(f"{service_url}/ops/pending")
                init_ops = [it for it in ops_init_resp.json() if it.get("rider_id") == rider_id]
            except Exception:
                init_ops = []

            all_agent_replies = []
            scenario_error = None
            t0 = time.time()

            for turn in turns:
                if turn.get("from") == "rider":
                    msg_payload = {
                        "message_id": turn.get("message_id", f"eval_{idx}_{time.time()}"),
                        "rider_id": rider_id,
                        "text": turn.get("text", ""),
                        "received_at": turn.get("received_at", "2026-09-23T10:00:00+05:30"),
                    }
                    try:
                        resp = client.post(f"{service_url}/messages", json=msg_payload)
                        if resp.status_code == 200:
                            reply_txt = resp.json().get("reply", "")
                            all_agent_replies.append(reply_txt)
                        else:
                            scenario_error = f"POST /messages returned {resp.status_code}: {resp.text}"
                            break
                    except Exception as e:
                        scenario_error = f"Failed POST /messages: {e}"
                        break

            duration_ms = int((time.time() - t0) * 1000)

            # After conversation, check new payouts from PaySwift
            try:
                psw_post_resp = client.get(f"{payswift_url}/v1/payouts", params={"rider_id": rider_id})
                post_payouts = sum(p.get("amount", 0) for p in psw_post_resp.json().get("data", []))
                actual_payout_diff = post_payouts - init_payouts
            except Exception:
                actual_payout_diff = 0

            # Check new items in ops/pending
            try:
                ops_post_resp = client.get(f"{service_url}/ops/pending")
                post_ops = [it for it in ops_post_resp.json() if it.get("rider_id") == rider_id]
                new_ops = post_ops[len(init_ops):] if len(post_ops) >= len(init_ops) else post_ops
            except Exception:
                new_ops = []

            # Validate expectations
            is_pass = True
            fail_reasons = []

            if scenario_error:
                is_pass = False
                fail_reasons.append(scenario_error)
            else:
                # Check one_of alternate outcomes if present
                if "one_of" in expected:
                    matches_one = False
                    for option in expected["one_of"]:
                        exp_pay = option.get("payout", 0)
                        exp_appr = option.get("approval")
                        appr_matched = False
                        if exp_appr is None:
                            appr_matched = not any(it.get("type") == "approval" for it in new_ops)
                        else:
                            appr_matched = any(it.get("type") == "approval" and it.get("amount") == exp_appr for it in new_ops)

                        if actual_payout_diff == exp_pay and appr_matched:
                            matches_one = True
                            break
                    if not matches_one:
                        is_pass = False
                        fail_reasons.append(f"Outcome (payout={actual_payout_diff}) did not match any option in one_of {expected['one_of']}")
                else:
                    # Direct check on expected.payout
                    exp_payout = expected.get("payout", 0)
                    if actual_payout_diff != exp_payout:
                        is_pass = False
                        fail_reasons.append(f"Payout mismatch: expected Rs.{exp_payout}, got Rs.{actual_payout_diff}")

                    # Check expected.approval
                    exp_approval = expected.get("approval")
                    if exp_approval is not None:
                        matching_appr = [it for it in new_ops if it.get("type") == "approval" and it.get("amount") == exp_approval]
                        if not matching_appr:
                            is_pass = False
                            fail_reasons.append(f"Ops approval mismatch: expected Rs.{exp_approval} pending")
                    else:
                        unwanted_appr = [it for it in new_ops if it.get("type") == "approval"]
                        if unwanted_appr:
                            is_pass = False
                            fail_reasons.append(f"Unexpected ops approval queued: {unwanted_appr}")

                # Check expected.escalation
                exp_escalation = expected.get("escalation", "no")
                has_escalation = any(it.get("type") == "escalation" for it in new_ops)
                if exp_escalation == "required" and not has_escalation:
                    is_pass = False
                    fail_reasons.append("Escalation required but none found in ops queue")
                elif exp_escalation == "no" and has_escalation:
                    is_pass = False
                    fail_reasons.append("Unexpected escalation item in ops queue")

                # Check reply mentions
                combined_replies = " ".join(all_agent_replies)
                mentions = expected.get("reply_mentions", [])
                if mentions and not check_reply_mentions(combined_replies, mentions):
                    is_pass = False
                    fail_reasons.append(f"Reply missing mentions: {mentions}")

            if is_pass:
                total_passed += 1

            status_str = "PASS" if is_pass else "FAIL"
            note_str = ", ".join(fail_reasons) if fail_reasons else "All criteria matched"
            print(f"  [{status_str}] #{idx+1:<2} {rider_id:<5} {sc_name[:35]:<35} Paid:{actual_payout_diff:<4} ({duration_ms}ms) -> {note_str}", flush=True)
            results.append({
                "idx": idx + 1,
                "rider": rider_id,
                "scenario": sc_name[:35],
                "status": status_str,
                "latency": f"{duration_ms}ms",
                "payout": f"Rs.{actual_payout_diff}",
                "notes": note_str
            })

        # Print Report Table
        print(f"\n{'#':<3} | {'Rider':<6} | {'Scenario':<35} | {'Status':<12} | {'Paid':<6} | {'Time':<7} | {'Details'}")
        print("-" * 90)
        for r in results:
            print(f"{r['idx']:<3} | {r['rider']:<6} | {r['scenario']:<35} | {r['status']:<12} | {r['payout']:<6} | {r['latency']:<7} | {r['notes']}")

        total_time = round(time.time() - total_start_time, 2)
        pass_rate = (total_passed / len(scenarios)) * 100

        print("=" * 90)
        print(f" SUMMARY: {total_passed}/{len(scenarios)} Passed ({pass_rate:.1f}%) | Total Time: {total_time}s")
        print("=" * 90 + "\n")

        return total_passed == len(scenarios)


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    success = run_evaluation(url)
    sys.exit(0 if success else 1)
