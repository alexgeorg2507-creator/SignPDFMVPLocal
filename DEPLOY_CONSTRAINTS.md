# SignFinder — Deploy Constraints

Операционные правила деплоя. Обновляется по мере накопления опыта.

---

## КАК РАБОТАЕТ КОДЕР-ЧАТ — ОБЯЗАТЕЛЬНО ПРОЧИТАТЬ

### Доступ к файлам

Кодер-чат имеет **прямой доступ к файлам проекта** через Filesystem MCP:
- `C:\work\signfinder-core\`
- `C:\work\signfinder-api\`
- `C:\work\SignPDFMVPLocal\`

**Читать файлы перед правкой — обязательно.** Никогда не угадывать структуру кода.

### КОД В ЧАТ НЕ ВЫВОДИТЬ — НИКОГДА

**ЗАПРЕЩЕНО** выводить код в чат. Всегда:
1. Изменить файл напрямую через Filesystem MCP (`write_file` / `edit_file`)
2. Вызвать `present_files` с путём к изменённому файлу
3. Дать пользователю ссылку + путь в проекте

**Формат ответа после изменений:**
```
ОБНОВЛЁННЫЕ: [filename.py](ссылка) → C:\work\...\filename.py
НОВЫЕ: [filename.py](ссылка) → C:\work\...\filename.py
```

Код в чате — это трата токенов и контекста. Пользователь не читает код в чате.

### ПОСЛЕ ИЗМЕНЕНИЙ — КОМАНДЫ ДЛЯ ПОЛЬЗОВАТЕЛЯ

После каждого изменения файлов выдать пользователю:
1. Команду `git add / commit / push` (если менялся core или api)
2. Команду деплоя (см. матрицу ниже)

---

## СРЕДА ВЫПОЛНЕНИЯ — WINDOWS POWERSHELL

**Пользователь работает в Windows PowerShell, НЕ в bash.**

### Критические различия

| Bash (НЕЛЬЗЯ) | PowerShell (ПРАВИЛЬНО) |
|---------------|------------------------|
| `cmd1 && cmd2` | Две отдельные строки |
| `cmd1 \|\| cmd2` | Не использовать |
| `export VAR=value` | `$env:VAR = "value"` |
| `cat file` | `Get-Content file` |
| `grep pattern` | `Select-String "pattern"` |
| `head -n 10` | `Select-Object -First 10` |
| `rm -rf dir` | `Remove-Item -Recurse -Force dir` |

### Правило деплоя в PowerShell — команды ОТДЕЛЬНЫМИ СТРОКАМИ

```powershell
# ПРАВИЛЬНО — каждая команда отдельно
cd C:\work\SignPDFMVPLocal
docker compose build api
docker compose up -d --force-recreate api

# НЕПРАВИЛЬНО — && не работает в PowerShell как ожидается
docker compose build api && docker compose up -d
```

---

## Структура репо (одна точка истины)

```
C:\work\
├── .dockerignore                    ← В КОРНЕ C:\work\ — обязательно
├── signfinder-core\                 ← pip-пакет, бизнес-логика
│   └── signfinder\__init__.py       ← __version__ — бампить при каждом коммите
├── signfinder-api\                  ← ЕДИНСТВЕННАЯ точка истины для кода API
│   └── app\                         ← Весь FastAPI код пишется ТОЛЬКО сюда
└── SignPDFMVPLocal\
    ├── api\
    │   └── Dockerfile               ← Только Dockerfile, кода нет
    ├── streamlit\
    ├── data\api\                    ← Шаблоны, конфиги, подпись, llm_config.json
    └── docker-compose.yml
```

**Правило:** `SignPDFMVPLocal/api/` содержит только `Dockerfile`. Никакого кода.
**Правило:** Любое изменение API — только в `signfinder-api/app/`.
**Правило:** Перед тем как писать файл — проверить Dockerfile куда он копирует.

---

## Версионирование signfinder-core

**Правило:** любой коммит в `signfinder-core` = bump версии.

- Минорный: `1.10.0 → 1.10.1` (фикс, мелкое изменение)
- Мажорный: `1.10.x → 1.11.0` (новая версия по roadmap)

Версия прописывается в:
- `signfinder/__init__.py` → `__version__ = "1.10.x"`
- `pyproject.toml` → `version = "1.10.x"`

Версия должна быть видна:
- В логах API при старте: `INFO: SignFinder Core v1.10.x loaded`
- В Streamlit UI (футер или страница настроек)

### Команды git для core (PowerShell)

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.X.Y: описание изменения"
git push origin main
git log --oneline -1
```

---

## Docker: когда и как пересобирать

### Слои Dockerfile (правильная структура)

```dockerfile
# Слой 1 — зависимости (кэшируется, пересобирается редко)
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN pip install git+https://github.com/alexgeorg2507-creator/signfinder-core.git

# Слой 2 — код приложения (пересобирается только при изменении app/)
COPY signfinder-api/app/ /app/
```

### Матрица команд (PowerShell — каждая строка отдельно)

| Что изменилось | Команды |
|----------------|---------|
| Только `signfinder-api/app/` | `docker compose build api` → `docker compose up -d --force-recreate api` |
| `signfinder-core` + bump версии | `docker compose build api` → `docker compose up -d --force-recreate api` |
| `signfinder-core` без bump (костыль) | `docker compose build --no-cache api` → `docker compose up -d --force-recreate api` |
| Только `streamlit/` | `docker compose build streamlit` → `docker compose up -d --force-recreate streamlit` |
| И core и streamlit | Оба build отдельно → `docker compose up -d --force-recreate` |

### Проверка после деплоя

```powershell
docker compose logs api 2>&1 | Select-Object -First 15
```

Ожидаем: `SignFinder API starting up...` (без "local mode") + `SignFinder Core vX.Y.Z loaded`.

**Важно:** `docker compose up -d` без `--force-recreate` не перезапускает живой Healthy контейнер
даже если образ обновился. Всегда использовать `--force-recreate` после `build`.

---

## .dockerignore (C:\work\.dockerignore)

Файл лежит в корне `C:\work\` — не в `SignPDFMVPLocal\`.
Docker ищет `.dockerignore` по контексту сборки (`context: ..`), не по рабочей директории.
Без него Docker тянет весь контекст включая `.git` и лишние репо.

**Актуальное содержимое:**
```
**/.git
**/__pycache__
**/*.pyc
**/venv
**/.venv
SignPDFMVPLocal/data
SignPDFMVP
**/*.egg-info
```

`signfinder-api` — НЕ исключать. Dockerfile копирует из него код API.

---

## StorageBackend API — обязательно читать перед написанием роутеров

**Правило:** перед написанием любого роутера в `signfinder-api/app/` — открыть
`signfinder-core/signfinder/storage/base.py` и использовать только методы из протокола.

### Допустимые методы `sf.storage.*`

| Метод | Сигнатура | Описание |
|-------|-----------|----------|
| `read_bytes` | `(path: str) → Optional[bytes]` | Читает файл. **None если не существует** |
| `write_bytes` | `(path: str, data: bytes) → None` | Пишет файл, создаёт папки |
| `read_text` | `(path: str) → Optional[str]` | Читает UTF-8. None если нет |
| `write_text` | `(path: str, content: str) → None` | Пишет UTF-8, создаёт папки |
| `read_json` | `(path: str) → Optional[dict]` | Читает JSON. None если нет |
| `write_json` | `(path: str, data: dict) → None` | Пишет JSON indent=2 |
| `exists` | `(path: str) → bool` | Проверяет существование |
| `delete` | `(path: str) → bool` | Удаляет. True если удалён |
| `list_prefix` | `(prefix: str) → list[str]` | Список файлов по префиксу |

### Методов НЕТ (не выдумывать)

`sf.storage.read()`, `sf.storage.write()`, `sf.storage.get()`, `sf.storage.put()` — **не существуют**.
Написание несуществующего метода не падает при импорте — только в рантайме при первом вызове.

### Паттерн чтения с fallback

```python
# ПРАВИЛЬНО
raw = sf.storage.read_bytes("signers/default/profile.json")
data = json.loads(raw) if raw is not None else {"id": "default"}

# ПРАВИЛЬНО — проверка существования
has_sig = sf.storage.exists("signers/default/signature.png")

# НЕПРАВИЛЬНО — метода нет, упадёт в рантайме
data = sf.storage.read("signers/default/profile.json")
```

---

## Частые ошибки

| Ошибка | Симптом | Решение |
|--------|---------|---------| 
| Выводит код в чат | Токены потрачены, пользователь не читает | Записать файл через Filesystem MCP |
| `&&` в PowerShell | Команда не выполняется или ошибка синтаксиса | Две отдельные строки |
| Писал код не туда | Лог показывает старое поведение после деплоя | Проверить Dockerfile, найти реальный путь |
| Забыл bump версии | `pip` взял кэш старой версии core | `--no-cache` или bump + обычный build |
| `.dockerignore` не в корне `C:\work\` | Долгий билд, Docker тянет лишнее | Переложить в `C:\work\` |
| `signfinder-api` в `.dockerignore` | `COPY signfinder-api/app/` падает с `not found` | Убрать из `.dockerignore` |
| Два места для одного файла | Путаница какой файл актуален | Один источник истины, см. структуру выше |
| `up -d` без `--force-recreate` | Лог показывает старый timestamp | Добавить `--force-recreate` |
| `sf.storage.read()` / `.write()` | `AttributeError` в рантайме | Использовать `read_bytes()` / `write_bytes()` |

---

## История изменений

| Дата | Версия | Что добавлено |
|------|--------|---------------|
| 2026-05 | v1.9 | Первые правила: .dockerignore, --no-cache |
| 2026-06 | v1.10 | Версионирование, матрица команд, одна точка истины для API |
| 2026-06 | v1.12 | StorageBackend API, --force-recreate, .dockerignore с signfinder-api |
| 2026-06 | v1.14 | Правила кодер-чата: файлы на диск не в чат; PowerShell vs bash |
