# SignFinder v1.17.11 — Агент читает mail_config.json (фикс «IMAP не настроен»)

Прочитай `C:\work\CLAUDE.md` перед началом.

---

## Баг

Агент Mail не работает: «Агент недоступен», poll-now → `503 IMAP не настроен`.
Но IMAP-тест в Настройки → Mail проходит.

## Корень

Рассинхрон источника конфига:
- **UI** (Настройки → Mail) сохраняет в `data/api/settings/mail_config.json`
- **API** читает оттуда → тест проходит
- **Агент** (`agent/app/config.py`) читает из **env vars** (`os.environ.get("IMAP_HOST")`),
  а в `.env` их нет → `IMAP_HOST=""` → агент считает что IMAP не настроен

Агент монтирует `./data/api:/data` (docker-compose), значит mail_config.json
доступен ему по пути **`/data/settings/mail_config.json`**.

## Задача

Агент должен читать IMAP/SMTP/папки из `mail_config.json` (приоритет),
с fallback на env vars. Изменения УИ должны подхватываться без пересборки —
читать JSON при каждом обращении, не кэшировать на уровне импорта.

---

## Файл 1 — `agent/app/config.py`

Добавить функцию загрузки из JSON с fallback на env:

```python
import json

MAIL_CONFIG_PATH = os.path.join(DATA_PATH, "settings", "mail_config.json")

def load_mail_config() -> dict:
    """Читает mail_config.json (приоритет) с fallback на env vars.
    Читается при каждом вызове — подхватывает изменения из UI без рестарта.
    """
    cfg = {}
    try:
        with open(MAIL_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cfg = {}

    def _get(json_key, env_key, default):
        val = cfg.get(json_key)
        if val not in (None, ""):
            return val
        return os.environ.get(env_key, default)

    return {
        "imap_host": _get("imap_host", "IMAP_HOST", ""),
        "imap_port": int(_get("imap_port", "IMAP_PORT", 993)),
        "imap_user": _get("imap_user", "IMAP_USER", ""),
        "imap_password": _get("imap_password", "IMAP_PASSWORD", ""),
        "imap_ssl": str(_get("imap_ssl", "IMAP_SSL", "true")).lower() in ("true", "1", "yes", "true"),
        "smtp_host": _get("smtp_host", "SMTP_HOST", ""),
        "smtp_port": int(_get("smtp_port", "SMTP_PORT", 587)),
        "smtp_user": _get("smtp_user", "SMTP_USER", ""),
        "smtp_password": _get("smtp_password", "SMTP_PASSWORD", ""),
        "folder_in": _get("folder_in", "FOLDER_IN", "SignfinderIn"),
        "folder_green": _get("folder_green", "FOLDER_GREEN", "SignfinderGreen"),
        "folder_yellow": _get("folder_yellow", "FOLDER_YELLOW", "SignfinderYellow"),
        "folder_red": _get("folder_red", "FOLDER_RED", "SignfinderRed"),
        "folder_archive": _get("folder_archive", "FOLDER_ARCHIVE", "SignfinderArchive"),
        "poll_interval_sec": int(_get("poll_interval_sec", "POLL_INTERVAL_SEC", 300)),
        "reply_to_sender": str(_get("reply_to_sender", "REPLY_TO_SENDER", "false")).lower() in ("true", "1", "yes"),
    }
```

Обрати внимание: `imap_ssl` в JSON приходит как bool `true`, а из env как строка
`"true"`. Хелпер должен корректно обработать оба. Проверь логику приведения.

Старые module-level константы (`IMAP_HOST = ...`) можно оставить для обратной
совместимости, но НЕ использовать их в mailbox/poller — там перейти на `load_mail_config()`.

## Файл 2 — `agent/app/mailbox.py`

Сейчас импортирует константы и кэширует `_source`. Переписать:

```python
from app.config import load_mail_config

_source = None
_source_key = None  # хэш конфига для инвалидации кэша

def _get_source():
    global _source, _source_key
    cfg = load_mail_config()
    if not cfg["imap_host"]:
        raise RuntimeError("IMAP не настроен (mail_config.json пуст и env пуст)")
    # Ключ для инвалидации: если конфиг изменился — пересоздать source
    key = (cfg["imap_host"], cfg["imap_port"], cfg["imap_user"], cfg["folder_in"])
    if _source is None or _source_key != key:
        from signfinder.intake.imap_source import ImapSource
        _source = ImapSource(
            host=cfg["imap_host"], port=cfg["imap_port"], user=cfg["imap_user"],
            password=cfg["imap_password"], ssl=cfg["imap_ssl"], folder_in=cfg["folder_in"],
        )
        _source_key = key
    return _source
```

Аналогично `_get_sink()` — читать SMTP из `load_mail_config()`.

Все места где используются `FOLDER_GREEN`, `FOLDER_RED`, `FOLDER_YELLOW`,
`FOLDER_ARCHIVE`, `FOLDER_IN`, `REPLY_TO_SENDER` — заменить на чтение из
`load_mail_config()` в момент использования (в `do_resolve`, `move_*`, `append_to_folder`).

## Файл 3 — `agent/app/main.py`

`_poll_loop()` и endpoints проверяют `IMAP_HOST` (env). Заменить на:
```python
from app.config import load_mail_config

# в _poll_loop:
cfg = load_mail_config()
if not cfg["imap_host"]:
    logger.warning("IMAP не настроен — poll loop отключён")
    return
# интервал тоже из конфига:
interval = cfg["poll_interval_sec"]

# в /status:
"imap_configured": bool(load_mail_config()["imap_host"]),

# в /poll-now и /resolve проверки:
if not load_mail_config()["imap_host"]:
    raise HTTPException(status_code=503, detail="IMAP не настроен")
```

## Файл 4 — `agent/app/poller.py`

Где `from app.config import FOLDER_YELLOW` — заменить на чтение из `load_mail_config()`.

---

## Проверка «Агент недоступен»

После фикса проверь что Streamlit (страница Агент Mail) корректно достучивается
до agent:9000/status. Если «Агент недоступен» осталось — посмотри как UI зовёт
статус (через API-прокси `/v1/agent/status` или напрямую). Должно вернуть
`imap_configured: true` после фикса.

---

## Bump + деплой

```powershell
cd C:\work\SignPDFMVPLocal
docker compose build agent
docker compose up -d --force-recreate agent
docker compose logs agent 2>&1 | Select-Object -First 20
```

(core не менялся — без git push)

Версия агента → 1.17.11 в main.py.

## Тест

1. Агент Mail → «Опросить почту сейчас» → НЕ должно быть «IMAP не настроен»
2. Статус показывает imap_configured
3. Положить договор в SignfinderIn (Gmail) → опросить → обработка
4. Лог агента: `docker compose logs agent` — видно poll, messages count

---

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
