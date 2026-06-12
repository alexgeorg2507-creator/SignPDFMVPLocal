import json, shutil, datetime

with open('data/signer_profile.json', encoding='utf-8') as f:
    old = json.load(f)

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
shutil.copy('data/signer_profile.json', f'data/backups/signer_profile_{ts}_old.json')

company = ''
signer = ''

for a in old.get('company_aliases', []):
    if a.get('language') == 'ru':
        company = a.get('value', '').strip()
        break

for a in old.get('signer_aliases', []):
    if a.get('language') == 'ru':
        signer = a.get('value', '').strip()
        break

new = {
    'id': 'default',
    'name': signer,
    'company': company,
    'position': '',
    'company_aliases': old.get('company_aliases', []),
    'signer_aliases': old.get('signer_aliases', [])
}

with open('data/signer_profile.json', 'w', encoding='utf-8') as f:
    json.dump(new, f, ensure_ascii=False, indent=2)

print('Готово')
print('  name: ' + new['name'][:50])
print('  company: ' + new['company'][:50])
