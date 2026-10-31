# QuickDrop Rider Payout Dispute Desk

Production-grade conversational AI dispute resolution desk for QuickDrop riders with deterministic financial guardrails, multi-turn memory, PaySwift chaos resilience, and an interactive Ops Review Portal.

<p align="center">
  <img src="demo.png" alt="QuickDrop Ops Dispute Desk & WhatsApp Simulator Demo" width="100%" />
</p>

---

### Quick Start

```bash
# 1. Start all services (App on :8000, PaySwift on :8081, PostgreSQL on :5432)
docker compose up --build

# 2. Run the full evaluation benchmark (one-liner)
python evals/run.py http://localhost:8000

# 3. Open the Ops Portal & WhatsApp Web Simulator in your browser
open http://localhost:8000/
```

---

### Agent Architecture: Model vs. Code Boundary

To guarantee zero financial hallucination while preserving natural conversational empathy in Hinglish, the system adheres to a strict division of responsibility:

```
Rider (WhatsApp) ──> Perception Layer ──> Deterministic Firewall ──> Resilient PaySwift / Ops Queue
                     (Intent/Entity)       (Policy Math in Code)      (Idempotency + Chaos Retries)
```

1. **What Code Decides (Deterministic Financial Firewall)**:
   - **Policy Calculations**: Base fare (₹25 for $\le 2$ km), incremental rate (₹6/km), whole-trip surge multiplier, and strict half-up rounding (`ROUND_HALF_UP`).
   - **Ledger Discrepancy Reconciliation**: Direct SQL/domain comparison between expected policy earnings and actual `payout_lines` credits.
   - **Financial Guardrails**: Max ₹200 auto-payout per dispute, max 1 auto-payout per rider per calendar day (IST). Any excess or repeat payouts are strictly locked in code and routed to `GET /ops/pending` (`type="approval"`).
   - **Safety & Escalations**: Accidents, medical emergencies, and GPS hardware tracking discrepancies are escalated to ops (`type="escalation"`).
   - **Security Firewall**: Prompt injections (`system:`, override commands) and cross-rider impersonation attempts are automatically blocked.

2. **What the Model Decides (Perception & Conversational Synthesis)**:
   - Parsing messy rider messages across code-switched Hindi-English ("kal ka payout kam aaya", "20 wala check karo").
   - Extracting temporal anchors ("kal", "18 tarikh", "pichle hafte") and order identifiers (`T...`).
   - Synthesizing empathetic, culturally natural Hinglish explanations detailing fare breakdowns, surge calculations, and ops approval statuses.

---

### Tools Provided to Agent

- `evaluate_rider_discrepancies(rider_id, target_date, target_trip_ids, reference_date)`: Deterministic policy reconciliation returning exact math and breakdown.
- `execute_payout_or_queue(rider_id, amount, reason)`: Autonomous disbursement through PaySwift if within limits; otherwise automatically creates an ops approval ticket.
- `escalate_to_ops(rider_id, type, reason)`: Surfaces manual intervention tickets for accidents, tracking disputes, or prompt injections.
- `record_audit_trace(rider_id, type, name, input, output)`: Logs audit trail strictly adhering to `SUBMISSION.md` schema.

---

### Evaluation Benchmark Results

Evaluated against all 24 real-world test scenarios from `data/conversations.json` with active PaySwift server chaos injection:

```
==========================================================================================
 SUMMARY: 24/24 Passed (100.0%) | Total Time: 113.47s | Zero Financial Errors
==========================================================================================
```
- **Payout Precision**: 100% exact rupee-level match across all single-order, multi-order, and surge disputes.
- **Ops Guardrails**: 100% accurate queueing of large disputes (₹425, ₹249) and second daily disputes (₹10).
- **Chaos Resilience**: 100% tolerance against PaySwift 503 Service Unavailable, 504 Timeouts, and 429 rate limits using exponential backoff with full jitter and pure-ASCII sanitized references.
- **Trace Compliance**: 100% adherence to `SUBMISSION.md` output formats for `GET /trace/{rider_id}` and `GET /ops/pending`.

---

### Ops Portal & WhatsApp Simulator

An interactive, responsive single-page portal is served directly at `http://localhost:8000/`:
- **WhatsApp Web Simulator**: Test any rider ID (`R001`-`R040`) without requiring a personal WhatsApp account.
- **Trace Visualizer**: Live, color-coded timeline of `message_in`, `tool_call`, `decision`, and `reply` steps.
- **Ops Review Desk**: Review pending approvals and escalations, and trigger one-click approval or rejection.
- **PaySwift Ledger Stream**: Live audit view of disbursements made to the PaySwift provider.

---

### Key Assumptions & System Nuances

1. **Reference Time Anchor**: Disputes evaluate relative to the incoming message timestamp (`received_at`), ensuring historical test scenarios (September 2026) evaluate within their legitimate 7-day lookback window.
2. **Trips Distance Normalization**: Riders `R031`, `R032`, `R038`, `R039`, and `R040` had distance recorded in meters (> 100). The data loader automatically normalizes these to kilometers.
3. **Idempotency & Vendor Retry Guarantee**: Double-delivery of identical message IDs returns cached responses immediately with zero duplicate calls to PaySwift.
4. **Pure ASCII Reference Sanitation**: PaySwift rejects Unicode characters in `reference` payloads; the client automatically sanitizes references before dispatch.

---

### What Was Skipped / Trade-offs

- **External WhatsApp Cloud API Integration**: Skipped live Meta webhook verification token handshake; provided identical `POST /messages` interface with a rich Web Chat Simulator so anyone can test the system locally.
- **Voice/Audio Notes**: Text/Hinglish messaging was prioritized given the assessment specification.
