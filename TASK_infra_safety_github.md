# SignFinder — Сохранность инфры: api и local на GitHub (НЕ заморозка)

Прочитай `C:\work\CLAUDE.md` перед началом.

ЦЕЛЬ: загнать `signfinder-api` и `SignPDFMVPLocal` под git и на GitHub. Сейчас они
живут ТОЛЬКО на диске — это риск. Это НЕ заморозка/теги/форк (то будет отдельно).
Просто привести инфру под контроль версий.

GitHub: `alexgeorg2507-creator`. Создать репозитории заранее через веб (пустые,
без README/gitignore): `signfinder-api`, `signfinder-local`.

ПРЕДОХРАНИТЕЛЬ: перед каждым `git push` — `git status` и глазами проверить что НЕТ
`.env`, ключей, паролей, подписей, писем. Если видишь секрет в списке — СТОП, добавь
в .gitignore, не коммить.

Бэкап всего C:\work\ уже сделан пользователем.

---

## Шаг 1 — core: закоммитить хвост (он почти синхронизирован)

core на main, синхронизирован с origin. Незакоммичено только 2 документа.

```powershell
cd C:\work\signfinder-core
git add TECH_DEBT.md RELEASE_STRATEGY.md
git commit -m "docs: TD-06 update (OAuth2 secrets), release strategy"
git push origin main
```

### Заодно починить сломанный .gitignore
Текущий `signfinder-core/.gitignore` содержит невыполнившуюся PowerShell-команду
(`@"..."@ | Out-File`) вместо чистого содержимого. Переписать на нормальный:
```
__pycache__/
*.py[cod]
*.so
build/
dist/
*.egg-info/
.eggs/
venv/
env/
ENV/
.venv/
.vscode/
.idea/
*.swp
.DS_Store
Thumbs.db
.pytest_cache/
.coverage
htmlcov/
.tox/
.env
.env.local
signfinder_data/
test_data/
```
```powershell
git add .gitignore
git commit -m "fix: clean .gitignore (was broken heredoc artifact)"
git push origin main
```

---

## Шаг 2 — signfinder-api: убрать мусор, git init, push

### 2.1 Удалить фантомную папку (пустой артефакт брейс-экспансии)
```powershell
Remove-Item "C:\work\signfinder-api\app\{models,routers}" -Recurse -Force
```

### 2.2 Дополнить .gitignore — добавить рантайм-данные
В `signfinder-api/.gitignore` добавить строку (сейчас её нет):
```
signfinder_jobs/
```
(там job.json — рантайм обработки, не код. .env реального нет, только .example — ок.)

### 2.3 git init + первый коммит + push
```powershell
cd C:\work\signfinder-api
git init
git add -A
git status
```
**СТОП. Проверить вывод git status:** в списке НЕ должно быть `.env`, `venv/`,
`signfinder_jobs/`, `__pycache__/`, `{models,routers}`. Должны быть: app/ (код),
Dockerfile, pyproject.toml, .env.example, README.md, cloudbuild.yaml, .gitignore.
Если что-то лишнее — поправить .gitignore, `git rm --cached`, перепроверить.

После проверки:
```powershell
git commit -m "Initial commit: signfinder-api (FastAPI layer, v1.18.0 state)"
git branch -M main
git remote add origin https://github.com/alexgeorg2507-creator/signfinder-api.git
git push -u origin main
```

---

## Шаг 3 — SignPDFMVPLocal: git init, push (ОСТОРОЖНО — здесь реальные секреты)

`SignPDFMVPLocal/.gitignore` УЖЕ правильный (игнорит `.env`, `data/api/`, `data/jobs/`,
`data/streamlit-config/`). Здесь лежит реальный `.env` с API_KEY и паролями Gmail,
а в `data/api/` — ключи LLM, mail_config с OAuth-токенами, подпись, письма клиента.
.gitignore их ловит, но ПРОВЕРИТЬ обязательно.

### 3.1 Почистить рабочий мусор (опционально, можно позже)
Эти файлы — артефакты рабочих сессий, в релиз не нужны (но НЕ секреты, можно и
оставить, реши сам):
```
TASK_*.md, test_sig.png, convert_*.py, batch_processing_ui_concept.html
```
Для первого коммита-сохранности можно НЕ удалять — главное не потерять код.
Чистку оставить на этап заморозки.

### 3.2 git init + проверка + push
```powershell
cd C:\work\SignPDFMVPLocal
git init
git add -A
git status
```
**СТОП. КРИТИЧНО — проверить git status:** в списке на коммит НЕ должно быть:
- `.env` (реальный, с паролями)
- `data/api/` (ключи, mail_config, подпись, письма)
- `data/jobs/`, `data/streamlit-config/`

Если `.gitignore` сработал — этих путей в списке НЕ будет. Если ВИДИШЬ их в списке —
СТОП, не коммить, разобраться почему .gitignore не поймал.

Должны быть: agent/, api/Dockerfile, streamlit/, docker-compose.yml, *.md,
.env.example, get_refresh_token.py, .gitignore.

После проверки:
```powershell
git commit -m "Initial commit: SignFinder local orchestration (v1.18.0 state)"
git branch -M main
git remote add origin https://github.com/alexgeorg2507-creator/signfinder-local.git
git push -u origin main
```

---

## Результат после этих 3 шагов

- core: полностью синхронизирован с GitHub + чистый .gitignore
- api: под git, на GitHub, без мусора и секретов
- local: под git, на GitHub, секреты НЕ утекли

Весь код MVP теперь на GitHub, а не только на диске. Риск потери закрыт.

## ЧЕГО НЕ ДЕЛАЕМ в этой задаче

- НЕ ставим теги (v1.18.0) — отдельным заходом
- НЕ морозим форк, НЕ трогаем Dockerfile (pin) — отдельным заходом
- НЕ переключаем сборку на git pip — это этап заморозки

Сначала просто сохранность. Теги и заморозка — следующим промптом, когда всё на GitHub.

## Стиль

Коротко, технично, по-русски. Это git/инфра — показывай команды и git status.
Перед каждым push секретов — СТОП и проверка глазами.
