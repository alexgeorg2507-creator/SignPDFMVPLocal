# SignFinder — GitHub push: signfinder-api + SignPDFMVPLocal + signfinder-core sync

Прочитай `C:\work\CLAUDE.md` перед началом.
Это git-инфраструктурная задача. Alex пушит вручную после коммитов.

ВАЖНО: репозитории PUBLIC на GitHub. Никаких секретов в коммит.
Перед каждым `git add -A` — `git status` и глазами проверить список.

---

## ПОДГОТОВКА — выполнить ДО git init

### 1. Исправить .gitignore signfinder-core (heredoc-артефакт)

Файл C:\work\signfinder-core\.gitignore содержит невыполнившуюся PS-команду
вместо нормального содержимого. Перезаписать чистым содержимым:

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

### 2. Добавить в .gitignore signfinder-api

Добавить строки в C:\work\signfinder-api\.gitignore:
```
signfinder_jobs/
```

### 3. Дополнить .gitignore SignPDFMVPLocal

Добавить строки в C:\work\SignPDFMVPLocal\.gitignore (данные в корне data/):
```
data/
test_sig.png
_trash_part1_fixed.md
```

ВАЖНО: нельзя исключать `data/api/` отдельно если мы исключаем весь `data/`.
Убедиться что в .gitignore нет дублирующих строк после добавления.

### 4. Удалить мусорные файлы из SignPDFMVPLocal

```powershell
Remove-Item "C:\work\SignPDFMVPLocal\test_sig.png" -Force -ErrorAction SilentlyContinue
Remove-Item "C:\work\SignPDFMVPLocal\_trash_part1_fixed.md" -Force -ErrorAction SilentlyContinue
Remove-Item "C:\work\SignPDFMVPLocal\batch_processing_ui_concept.html" -Force -ErrorAction SilentlyContinue
```

### 5. Удалить фантомную папку в signfinder-api

```powershell
Remove-Item "C:\work\signfinder-api\app\{models,routers}" -Recurse -Force -ErrorAction SilentlyContinue
```

---

## ШАГ 1 — signfinder-core: обновить коммит

core уже git-репозиторий, уже на GitHub. Просто синхронизировать последние изменения.

```powershell
cd C:\work\signfinder-core
git add -A
git status
```

СТОП. Проверить что в списке нет: .env, venv/, signfinder_data/
Должны быть: исправленный .gitignore, PERFORMANCE_ANALYSIS_v1.18.md,
RELEASE_STRATEGY.md, SIGNATURE_POSITIONING_ALGORITHM.md, TECH_DEBT.md,
изменения в signfinder/, tests/

```powershell
git commit -m "v1.18.23: stabilization complete — tests, columns, profiles, clustering"
git tag v1.18.23
```

(push — Alex делает вручную)

---

## ШАГ 2 — signfinder-api: git init + первый коммит

```powershell
cd C:\work\signfinder-api
git init
git add -A
git status
```

СТОП. Проверить список — должны быть: app/, Dockerfile, pyproject.toml, README.md,
cloudbuild.yaml, .env.example, .gitignore
НЕ должно быть: venv/, signfinder_jobs/, любых .env с реальными ключами

```powershell
git commit -m "Initial commit: signfinder-api FastAPI layer v1.18.23"
git branch -M main
git remote add origin https://github.com/alexgeorg2507-creator/signfinder-api.git
git tag v1.18.23
```

(push — Alex делает вручную: `git push -u origin main` + `git push origin v1.18.23`)

---

## ШАГ 3 — SignPDFMVPLocal: git init + первый коммит

```powershell
cd C:\work\SignPDFMVPLocal
git init
git add -A
git status
```

СТОП. КРИТИЧЕСКИ ВАЖНО проверить что в списке НЕТ:
- .env (реальный файл с паролями Gmail, API ключами)
- data/ (подписи, конфиги, шаблоны, письма)
- test_sig.png
- _trash_part1_fixed.md

Должны быть: agent/, api/Dockerfile, streamlit/, docker-compose.yml,
DEPLOY_CONSTRAINTS.md, GMAIL_SETUP.md, OAUTH2_SETUP.md,
MULTILLM_PROMPTS_DECISION.md, README.md, get_refresh_token.py,
TASK_*.md (рабочие промпты — не секрет, оставляем), .env.example, .gitignore

Если .env или data/ есть в списке — СТОП, разобраться с .gitignore.

```powershell
git commit -m "Initial commit: SignFinder local orchestration v1.18.23 (api+streamlit+agent)"
git branch -M main
git remote add origin https://github.com/alexgeorg2507-creator/SignPDFMVPLocal.git
git tag v1.18.23-local
```

(push — Alex делает вручную: `git push -u origin main` + `git push origin v1.18.23-local`)

---

## После пушей (Alex делает вручную)

```powershell
# signfinder-core
cd C:\work\signfinder-core
git push origin main
git push origin v1.18.23

# signfinder-api
cd C:\work\signfinder-api
git push -u origin main
git push origin v1.18.23

# SignPDFMVPLocal
cd C:\work\SignPDFMVPLocal
git push -u origin main
git push origin v1.18.23-local
```

---

## Проверка после пушей

Открыть в браузере:
- https://github.com/alexgeorg2507-creator/signfinder-core — должны быть новые коммиты
- https://github.com/alexgeorg2507-creator/signfinder-api — первый коммит
- https://github.com/alexgeorg2507-creator/SignPDFMVPLocal — первый коммит

Убедиться что в каждом репозитории на GitHub НЕТ:
- .env файлов с реальными значениями
- data/ папки с подписями/ключами/шаблонами
- signature.png

---

## Стиль

Коротко, технично, по-русски. Это git/инфра — показывай git status перед каждым commit.
СТОП перед каждым push и проверка глазами.
