import json

data = json.load(open('data/conversations.json', encoding='utf-8'))
for i, s in enumerate(data):
    exp = s.get('expected', {})
    turns = s.get('turns', [])
    first_rider_text = next((t['text'] for t in turns if t['from'] == 'rider'), '')
    last_rider_text = [t['text'] for t in turns if t['from'] == 'rider'][-1]
    one_of = exp.get("one_of")
    print(f"#{i+1:02d} | Rider: {s['rider_id']:<5} | Payout: {exp.get('payout')!s:<5} | Appr: {exp.get('approval')!s:<5} | Esc: {exp.get('escalation')!s:<8} | 1of: {bool(one_of)!s:<5} | Mentions: {exp.get('reply_mentions')}")
    print(f"     First: {first_rider_text}")
    if last_rider_text != first_rider_text:
        print(f"     Last:  {last_rider_text}")
