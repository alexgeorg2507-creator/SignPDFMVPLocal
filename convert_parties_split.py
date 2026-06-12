import json, os, sys

with open('data/api/parties.json', encoding='utf-8') as f:
    content = f.read().lstrip('\ufeff')
    parties = json.loads(content)

encoding = 'utf-8'
count = 0
for party in parties:
    name = party.get('name', '')
    if not name:
        continue
    filename = f"data/api/parties/{name}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(party, f, ensure_ascii=False, indent=2)
    count += 1

print(f'Created {count} party files')
