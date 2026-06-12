import json, shutil, datetime

with open('data/parties.json', encoding='utf-8') as f:
    old = json.load(f)

new_parties = []
for name, party in old.get('parties', {}).items():
    for lang, lang_data in party.get('languages', {}).items():
        patterns = lang_data.get('patterns', [])
        if patterns:
            new_parties.append({
                'name': name,
                'language': lang,
                'patterns': patterns,
                'aliases': lang_data.get('aliases', []),
                'display': party.get('display', name)
            })

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
shutil.copy('data/parties.json', f'data/backups/parties_{ts}_old_format.json')

with open('data/parties.json', 'w', encoding='utf-8') as f:
    json.dump(new_parties, f, ensure_ascii=False, indent=2)

print('Конвертировано: ' + str(len(new_parties)) + ' записей')
