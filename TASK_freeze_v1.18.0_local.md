# SignFinder — Заморозка локальной версии v1.18.0 (git-теги + форк + pin)

Прочитай `C:\work\CLAUDE.md` и `C:\work\signfinder-core\RELEASE_STRATEGY.md` перед началом.

Это инфраструктурная задача (git, не код приложения). Цель: зафиксировать
локальный MVP как замороженный форк, core/api сделать общими git-зависимостями.

GitHub аккаунт: `alexgeorg2507-creator`
Репозитории: signfinder-core (есть), signfinder-api (создать), signfinder-local (создать)

---

## ВАЖНО — текущее состояние сборки

Все Dockerfile (`api/Dockerfile`, `agent/Dockerfile`, `streamlit/Dockerfile`)
ставят core из ЛОКАЛЬНОЙ папки:
```dockerfile
COPY signfinder-core/ /tmp/signfinder-core/
RUN pip install --no-cache-dir /tmp/signfinder-core/
```
И api-код: `COPY signfinder-api/app/ ./app/`. Build context = `C:\work\`.

Значит `SignPDFMVPLocal` НЕ самодостаточна — зависит от соседних папок в `C:\work\`.
Для заморозки по выбранной стратегии (git pip-зависимости по тегу) Dockerfile надо
переключить с локального COPY на `pip install git+...@v1.18.0`.

---

## Шаг 1 — Тегнуть signfinder-core

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.18.0: release point (XOAUTH2, RELEASE_STRATEGY)"
git tag v1.18.0
git push origin main
git push origin v1.18.0
```

Проверить: версия в `__init__.py` и `pyproject.toml` == 1.18.0.

---

## Шаг 2 — signfinder-api: git init + push + тег

`signfinder-api` сейчас НЕ git-репо. Создать:

```powershell
cd C:\work\signfinder-api
git init
git add -A
git commit -m "v1.18.0: initial commit (FastAPI layer)"
git branch -M main
git remote add origin https://github.com/alexgeorg2507-creator/signfinder-api.git
git push -u origin main
git tag v1.18.0
git push origin v1.18.0
```

(Репозиторий `signfinder-api` на GitHub под `alexgeorg2507-creator` создать заранее
через веб — пустой, без README/gitignore, чтобы push прошёл.)

Проверить `.gitignore` в signfinder-api: должны быть исключены `venv/`, `__pycache__/`,
`.env`, `signfinder_jobs/` (рантайм-данные). НЕ коммитить секреты.

Убедиться что `signfinder-api/pyproject.toml` корректен для установки через pip
(name, version=1.18.0, dependencies). Если pyproject не настроен на установку как
пакет — поправить, чтобы `pip install git+...signfinder-api.git@v1.18.0` работал
и ставил `app/` как импортируемый модуль ИЛИ оставить app/ копируемым (см. Шаг 4).

---

## Шаг 3 — Переключить Dockerfile на git pip по тегу

Чтобы форк был самодостаточным и воспроизводимым, заменить локальный COPY core
на установку из git по тегу. В ТРЁХ Dockerfile.

### api/Dockerfile
Заменить:
```dockerfile
COPY signfinder-core/ /tmp/signfinder-core/
RUN pip install --no-cache-dir /tmp/signfinder-core/
```
на:
```dockerfile
RUN pip install --no-cache-dir \
    git+https://github.com/alexgeorg2507-creator/signfinder-core.git@v1.18.0
```

Для api-кода — два варианта:
- **Вариант A (проще, рекомендую):** оставить `COPY signfinder-api/app/ ./app/`
  как сейчас, но api-код вкоммитить в форк локалки (вендоринг ТОЛЬКО api-обёртки,
  она тонкая). Тогда форк самодостаточен по api, core тянется из git.
- **Вариант B:** `pip install git+...signfinder-api.git@v1.18.0` если api оформлен
  как устанавливаемый пакет. Сложнее (app/ как модуль).

Рекомендую A: core — общая зависимость из git (часто переиспользуется), api —
тонкая обёртка, её снапшот в форке проще и не создаёт проблем с упаковкой.

### agent/Dockerfile
Заменить тот же блок COPY core на git pip @v1.18.0 (как в api).
Агентский код (`SignPDFMVPLocal/agent/app/`) остаётся в форке (он часть локалки).

### streamlit/Dockerfile
Проверить — если ставит core через COPY, заменить на git pip @v1.18.0 аналогично.

### docker-compose.yml + build context
Если context был `..` (`C:\work\`) ради доступа к `signfinder-core/` и
`signfinder-api/` — после перехода на git pip контекст можно сузить до самой
`SignPDFMVPLocal/` (для варианта A нужен доступ к `signfinder-api/app/` —
тогда вкопировать снапшот api/app внутрь форка). Проверить `.dockerignore`.

---

## Шаг 4 — SignPDFMVPLocal → git-форк signfinder-local

### 4.1 Почистить от рабочего мусора
Удалить (это рабочие артефакты сессий, не релиз):
```
TASK_*.md  (все)
test_sig.png
convert_parties.py, convert_parties_split.py, convert_signer.py
batch_processing_ui_concept.html
```
Оставить: `agent/`, `api/`, `streamlit/`, `data/` (без секретов!), `docker-compose.yml`,
`DEPLOY_CONSTRAINTS.md`, `GMAIL_SETUP.md`, `OAUTH2_SETUP.md`, `MULTILLM_PROMPTS_DECISION.md`,
`README.md`, `.env.example`, `get_refresh_token.py`.

### 4.2 .gitignore (КРИТИЧНО — не коммитить секреты/данные клиента)
```
.env
data/api/llm_config.json
data/api/settings/mail_config.json
data/api/signers/*/signature.png
data/api/agent/
data/api/templates/
data/api/parties.json
**/__pycache__
**/*.pyc
```
Оставить структуру `data/` с примерами-заглушками, но НЕ реальные ключи/подписи/
шаблоны/письма клиента. Проверить что `.env` (с реальным API_KEY и паролями) НЕ
попадёт в коммит — только `.env.example`.

### 4.3 git init + первый коммит + тег
```powershell
cd C:\work\SignPDFMVPLocal
git init
git add -A
git status   # ПРОВЕРИТЬ что нет .env, mail_config.json, signature.png, писем
git commit -m "v1.18.0-local: frozen local release (single-user Docker)"
git branch -M main
git remote add origin https://github.com/alexgeorg2507-creator/signfinder-local.git
git push -u origin main
git tag v1.18.0-local-release
git push origin v1.18.0-local-release
```
(Репозиторий `signfinder-local` создать на GitHub заранее, пустой.)

---

## Шаг 5 — Проверка воспроизводимости (главный тест)

После заморозки — собрать локалку С НУЛЯ, как это сделает клиент:
1. Склонировать `signfinder-local` в чистую папку (НЕ в C:\work\ рядом с core)
2. `docker compose build` — должен подтянуть core из git @v1.18.0 (не из соседней папки!)
3. `docker compose up -d`
4. Проверить логи: `SignFinder Core v1.18.0 loaded`
5. Прогнать smoke-тест: analyze + sign на тестовом PDF → 200

Если сборка падает на отсутствии `../signfinder-core/` — значит Dockerfile ещё
тянет локально, не из git. Это и есть критерий что заморозка сделана правильно:
**форк собирается без соседних папок C:\work\.**

---

## После заморозки (НЕ в этой задаче)

- core/api продолжают развиваться в своих репо (main едет вперёд)
- Новый repo `signfinder-cloud` ставит core/api @main, строит мультитенант
- Локалка остаётся на тегах v1.18.0 / v1.18.0-local-release навсегда

## Стиль

Коротко, технично, по-русски. Это git/инфра — показывай команды и результаты
проверок. Перед push секретов — СТОП и проверка git status.
