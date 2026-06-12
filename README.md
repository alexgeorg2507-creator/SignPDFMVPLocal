# SignFinder Local Docker

Полностью локальный стек для разработки и тестирования.
Два контейнера: **API** (FastAPI + signfinder-core) и **Streamlit** (UI).
GCS не нужен — всё хранится в `./data/`.

## Структура репо

```
SignPDFMVPLocal/
├── docker-compose.yml
├── .env.example          ← скопировать в .env
├── data/                 ← gitignored, создаётся автоматически
│   ├── api/              ← хранилище API (signers, templates, parties, settings)
│   ├── jobs/             ← async jobs временные файлы
│   └── streamlit-config/ ← конфиги Streamlit (corrections.md, prompts.json, markers.json)
├── api/
│   ├── Dockerfile
│   └── app/              ← полная копия signfinder-api
└── streamlit/
    ├── Dockerfile
    ├── requirements.txt
    ├── app.py            ← dashboard v1.9 (API-клиент)
    ├── core/             ← core модули (api_client.py + оригинальные)
    └── pages/            ← страницы v1.9 (migrated)
```

## Требования

- Docker Desktop (или Docker Engine + Compose plugin)
- Git (для clone signfinder-core при сборке API)
- Доступ к GitHub: `github.com/alexgeorg2507-creator/signfinder-core`
- Anthropic API ключ

## Первый запуск

### 1. Подготовить .env

```bash
cp .env.example .env
```

Открыть `.env` и заполнить:

```
ANTHROPIC_API_KEY=sk-ant-api03-...      # твой ключ
API_KEY=my_local_secret_key_abc123xyz   # придумай, минимум 20 символов
ACCESS_CODE=1234                         # код входа в Streamlit UI
```

### 2. Собрать и запустить

```bash
docker compose up --build
```

Первая сборка: ~5-10 минут (скачивает signfinder-core + зависимости).
Повторный запуск без изменений: ~30 сек.

### 3. Открыть

| Сервис | URL |
|---|---|
| Streamlit UI | http://localhost:8501 |
| API Swagger | http://localhost:8000/docs |
| API Healthz | http://localhost:8000/healthz |

## Ежедневная работа

```bash
# Запуск (фоном)
docker compose up -d

# Остановка
docker compose down

# Логи API
docker compose logs -f api

# Логи Streamlit
docker compose logs -f streamlit

# Перезапуск только Streamlit (после изменения pages/)
docker compose restart streamlit

# Полная пересборка (после изменения requirements.txt или Dockerfile)
docker compose up --build
```

## Данные и персистентность

Все данные хранятся в `./data/` (gitignored):

```
data/
├── api/
│   ├── signers/default/
│   │   ├── profile.json       ← данные подписанта (display_name, position)
│   │   └── signature.png      ← PNG подписи
│   ├── templates/             ← шаблоны договоров
│   ├── parties/               ← стороны договора
│   └── settings/              ← traffic-light config, markers config
├── jobs/                      ← async jobs (автоочищаются)
└── streamlit-config/
    ├── corrections.md         ← база корректировок
    ├── prompts.json           ← промпты LLM
    └── signer_profile.json    ← алиасы подписанта (company/signer aliases)
```

**Бэкапы**: `docker compose down` не удаляет данные. Для полного сброса:
```bash
rm -rf ./data/api ./data/jobs ./data/streamlit-config
```

## Конфигурация signfinder-core

По умолчанию API собирается с:
```
git+https://github.com/alexgeorg2507-creator/signfinder-core.git@main
```

Для другой ветки или форка:
```bash
# В .env добавить:
SIGNFINDER_CORE_REPO=git+https://github.com/YOUR_FORK/signfinder-core.git@dev
```

Или собрать с локальным core (если репо рядом):
```bash
# Расскомментировать в api/Dockerfile и добавить volume в docker-compose.yml
# COPY ../signfinder-core /signfinder-core
# RUN pip install /signfinder-core
```

## Отличия от prod (GCS)

| | Local Docker | Production (GCS) |
|---|---|---|
| Хранилище | `./data/` (filesystem) | GCS bucket |
| signfinder-core | без `[gcs]` экстры | с `[gcs]` экстрой |
| Async jobs | синхронные (inline) | Cloud Tasks |
| CORS | `*` | ограниченный список |
| Workers | 1 | N |

## Архитектура v1.9

```
[Browser]
    ↓ :8501
[Streamlit]  →  HTTP (Bearer token)  →  [FastAPI /v1/*]
                                              ↓
                                        [signfinder-core]
                                              ↓
                                        [./data/ volume]
```

Streamlit не вызывает LLM напрямую — всё через API.
Исключения (нет endpoint в API, TODO v1.9 Ч.5):
- `corrections.md` — читается/пишется локально в `streamlit-config/`
- `prompts.json` — аналогично
- `signer_profile.json` (алиасы) — аналогично

## Добавить документ для страницы Документация

Скопировать `.md` файл в `streamlit/pages/docs/` или смонтировать volume:
```yaml
# в docker-compose.yml под streamlit:
volumes:
  - ./docs:/app/docs:ro
```

## Тестирование API напрямую

```bash
export API_KEY=my_local_secret_key_abc123xyz

# Health
curl http://localhost:8000/healthz

# Список шаблонов
curl -H "Authorization: Bearer $API_KEY" http://localhost:8000/v1/templates

# Анализ документа
curl -X POST http://localhost:8000/v1/analyze \
  -H "Authorization: Bearer $API_KEY" \
  -F "file=@/path/to/contract.pdf" \
  -F "language=ru"
```

## Troubleshooting

**Streamlit не запускается — `Connection refused`**
→ API ещё стартует. Подождать 30-60 сек, проверить `docker compose logs api`.

**API падает с `signfinder module not found`**
→ Сборка завершилась с ошибкой. Проверить доступность GitHub репо:
```bash
docker compose build api --no-cache
```

**`API_KEY env var is not set`**
→ Файл `.env` не создан или не содержит `API_KEY`. Проверить:
```bash
cat .env | grep API_KEY
```

**Данные пропали после `docker compose down`**
→ Не должны пропадать — данные в `./data/`. Проверить:
```bash
ls -la ./data/api/
```

**DOCX не конвертируется**
→ LibreOffice в Streamlit контейнере. Проверить:
```bash
docker compose exec streamlit soffice --version
```
