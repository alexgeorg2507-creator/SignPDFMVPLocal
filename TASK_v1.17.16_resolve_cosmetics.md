# SignFinder v1.17.16 — Фикс resolve 500 (Gmail SELECT desync в move)

Прочитай `C:\work\CLAUDE.md` перед началом.

---

## Статус

Основной баг подписи ЗАКРЫТ (v1.17.15): /v1/sign возвращает 200 на всех
документах, включая multi-anchor (6-8 якорей). Письма подписываются.

Остался один реальный баг + косметика.

---

## Баг 1 (РЕАЛЬНЫЙ) — resolve/move падает с 500

При «Подтвердить»/«Отклонить» иногда 500:
```
imaplib.IMAP4.abort: command: SELECT => unexpected response:
b' UIDs valid...EXISTS...UIDNEXT 23...FLAGS...'
```

### Корень

`signfinder-core/signfinder/intake/imap_source.py`, метод `move()`.

`move()` вызывает `_connect()`, который при живом соединении (noop OK)
**переиспользует** его. Но после предыдущего `append()` соединение Gmail могло
остаться в рассинхроне буфера (Gmail шлёт многословные untagged-ответы).
Следующий `SELECT src` читает чужой хвост → abort.

Фикс 1.17.14 убрал SELECT из `_ensure_folder` и закрыл соединение в `poll()`,
но `move()` по-прежнему делает `SELECT src` на переиспользованном соединении.

### Фикс — move() на свежем соединении

Добавить метод принудительного реконнекта и использовать его в `move()`:

```python
def _reconnect(self) -> None:
    """Принудительно создаёт свежее соединение. Сбрасывает рассинхрон буфера."""
    if self._imap is not None:
        try:
            self._imap.logout()
        except Exception:
            pass
        self._imap = None
    self._connect()
```

В начале `move()` заменить `self._connect()` на `self._reconnect()`:

```python
def move(self, uid, dest_folder, source_folder=None):
    self._reconnect()   # свежее соединение — без рассинхрона от append/poll
    assert self._imap is not None
    src = source_folder or self._folder_in
    self._ensure_folder(dest_folder)
    typ, _ = self._imap.select(self._quote(src))
    if typ != "OK":
        raise RuntimeError(f"IMAP SELECT {src} failed: {typ}")
    # ... остальное без изменений (UID MOVE + fallback COPY)
```

Также в `append()` — заменить `self._connect()` на `self._reconnect()`, чтобы
каждая запись шла на чистом соединении (append вызывается после poll/fetch):

```python
def append(self, folder, raw_email):
    self._reconnect()   # свежее соединение
    assert self._imap is not None
    self._ensure_folder(folder)
    # ... остальное без изменений
```

Это надёжнее закрытия в poll() — каждая операция записи самодостаточна.

---

## Баг 2 (косметика) — markers.json BOM + рассинхрон путей

В логах API спам: `[settings] load_markers error: Unexpected UTF-8 BOM`.

Две проблемы:
1. Core читает `markers.json` из КОРНЯ storage (`_MARKERS_FILE = "markers.json"`
   в `signfinder-core/signfinder/pipeline/settings.py`), а UI пишет в
   `settings/markers.json`. Два разных файла.
2. Корневой `markers.json` имеет UTF-8 BOM → load_markers падает → откат на
   MARKERS_DEFAULTS (поэтому не фатально, но спамит лог).

### Фикс

В `settings.py`, функция чтения markers — читать JSON с поддержкой BOM.
Если storage.read_json не справляется с BOM, читать через read_bytes и
декодировать `utf-8-sig`:

```python
raw = storage.read_bytes(_MARKERS_FILE)
if raw is not None:
    text = raw.decode("utf-8-sig")  # utf-8-sig съедает BOM если он есть
    data = json.loads(text)
```

Унифицировать путь: определиться где лежит markers — в корне или settings/.
UI пишет в settings/markers.json, поэтому core должен читать оттуда же:
```python
_MARKERS_FILE = "settings/markers.json"
```
Проверь что UI (PUT /v1/settings/markers) и core читают ОДИН путь.

---

## Баг 3 (косметика) — время в журнале UTC → местное

Журнал агента хранит время в UTC (правильно). Streamlit-страница «Агент Mail»
→ вкладка «Журнал» показывает UTC, а надо местное (Asia/Tbilisi, UTC+4).

Файл: `SignPDFMVPLocal/streamlit/pages/6_Agent_Mail.py` (или как называется).
При отображении времени конвертировать UTC → местное:

```python
from datetime import datetime, timezone
import zoneinfo

def _fmt_ts(iso_utc: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(zoneinfo.ZoneInfo("Asia/Tbilisi"))
        return local.strftime("%d.%m %H:%M")
    except Exception:
        return iso_utc
```

Применить в рендере журнала и очереди (где показывается ts/received_at).
Хранение оставить UTC — конвертация только при отображении.

---

## Баг 4 (косметика) — нет индикации прогресса опроса

Кнопка «Опросить почту сейчас» — опрос фоновый (1.17.14), результат не сразу.
Оператор жмёт несколько раз. Добавить индикацию:

После нажатия показать `st.info("⏳ Опрос запущен, обновите через ~30 сек")`
или спиннер + автообновление статуса. Можно опросить GET /v1/agent/status
(поле running) и показывать «идёт опрос» пока running=true.

---

## Bump + деплой

Баг 1 — core (git + --no-cache). Баги 2-4 — api/streamlit.

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.17.16: move on fresh connection, markers BOM/path, log timezone"
git push origin main

cd C:\work\SignPDFMVPLocal
docker compose build --no-cache api
docker compose build agent streamlit
docker compose up -d --force-recreate
```

Bump: core `__init__.py` + `pyproject.toml` → 1.17.16, api main.py → 1.17.16,
CLAUDE.md → 1.17.16.

## Тест

1. Переобработать письма (очистить очередь, снять «прочитано», опросить)
2. Все 5 → подписанные PDF (green и yellow)
3. «Подтвердить» жёлтое → Yellow→Green БЕЗ 500
4. «Отклонить» → Yellow→Red без 500
5. Лог API без BOM-спама
6. Журнал показывает местное время (UTC+4)
7. «Опросить» показывает индикацию

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
