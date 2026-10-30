import json

with open("data/conversations.json", "r", encoding="utf-8") as f:
    scenarios = json.load(f)

for i, s in enumerate(scenarios):
    rider = s.get("rider_id")
    turns = s.get("turns", [])
    first_text = turns[0].get("text", "") if turns else ""
    expected = s.get("expected", {})
    print(f"[{i:02d}] Rider: {rider} | Turns: {len(turns)} | Exp: {expected}")
    print(f"     Text: {first_text[:80]}")
