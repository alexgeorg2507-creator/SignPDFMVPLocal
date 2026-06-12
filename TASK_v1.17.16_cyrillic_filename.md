# SignFinder v1.17.16 — Фикс 500 на /v1/sign (кириллица в filename) + resolve + косметика

Прочитай `C:\work\CLAUDE.md` перед началом.

---

## Баг 0 (ГЛАВНЫЙ БЛОКЕР) — 500 на /v1/sign для кириллических имён файлов

### Симптом

Документы с латинскими именами (`Contract_Support.pdf`, `BSS_contract.pdf`) →
подписываются (200). С кириллицей (`1Договор Лебедев А.П..pdf`,
`ДОГОВОР НА ОКАЗАНИЕ...pdf`) → **500**. Число якорей ни при чём — дело в имени.

### Корень (точный трейс)

`signfinder-api/app/routers/pipeline.py`, endpoint `sign_document`, ~строка 162:
```python
filename = f"signed_{file.filename or 'document.pdf'}"
return Response(
    content=signed_bytes, media_type="application/pdf",
    headers={"Content-Disposition": f'attachment; filename="{filename}"'},
)
```

HTTP-заголовки кодируются в latin-1. Кириллица в `filename` →
`UnicodeEncodeError: 'latin-1' codec can't encode...` → 500.

`sf.sign()` отрабатывает успешно — PDF генерируется. Падение на отдаче ответа.

### Фикс — RFC 5987 (filename* с UTF-8 percent-encoding)

```python
from urllib.parse import quote

# ASCII-fallback для filename= + RFC5987 filename*= для UTF-8
raw_name = f"signed_{file.filename or 'document.pdf'}"
ascii_name = raw_name.encode("ascii", "replace").decode("ascii")  # ? вместо кириллицы
utf8_name = quote(raw_name)  # percent-encoded UTF-8

return Response(
    content=signed_bytes,
    media_type="application/pdf",
    headers={
        "Content-Disposition": (
            f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{utf8_name}"
        )
    },
)
```

Это даёт ASCII-имя для старых клиентов + корректное UTF-8 имя (RFC 5987) для
современных. Заголовок кодируется в latin-1 без ошибок (всё ASCII + percent-encoding).

### Проверить другие Response с filename

Поиск по `signfinder-api/app/` других мест где `filename` из пользовательского
ввода идёт в заголовок Content-Disposition (preview, batch, jobs). Применить
тот же RFC 5987 паттерн везде где имя может быть кириллическим.

---

## Баг 1 — resolve/move падает с 500 (Gmail SELECT desync)

`signfinder-core/signfinder/intake/imap_source.py`, метод `move()`.

При «Подтвердить»/«Отклонить» иногда 500:
```
imaplib.IMAP4.abort: SELECT => unexpected response: b' UIDs valid...UIDNEXT 23...FLAGS'
```

`move()` переиспользует соединение (noop OK), но после `append()` Gmail оставил
рассинхрон буфера → SELECT читает чужой хвост → abort.

### Фикс — move() и append() на свежем соединении

Добавить метод:
```python
def _reconnect(self) -> None:
    """Принудительно свежее соединение. Сбрасывает рассинхрон буфера Gmail."""
    if self._imap is not None:
        try:
            self._imap.logout()
        except Exception:
            pass
        self._imap = None
    self._connect()
```

В `move()` и `append()` заменить первый вызов `self._connect()` на `self._reconnect()`.
Резолюция/запись нечастые — лишний логин не критичен, надёжность важнее.

---

## Баг 2 (косметика) — markers.json BOM + рассинхрон путей

Лог API спамит: `[settings] load_markers error: Unexpected UTF-8 BOM`.

Core читает `markers.json` из корня storage, UI пишет в `settings/markers.json` —
разные файлы. Корневой с BOM → load_markers падает → откат на дефолты (не фатально).

### Фикс
В `signfinder-core/signfinder/pipeline/settings.py`:
1. Читать markers с поддержкой BOM:
   ```python
   raw = storage.read_bytes(_MARKERS_FILE)
   data = json.loads(raw.decode("utf-8-sig")) if raw else None
   ```
2. Унифицировать путь: `_MARKERS_FILE = "settings/markers.json"` (туда же пишет UI).
   Проверить что PUT /v1/settings/markers и core читают один путь.

---

## Баг 3 (косметика) — время журнала UTC → местное

Streamlit-страница агента показывает UTC. Конвертировать в Asia/Tbilisi (UTC+4)
при отображении (хранение оставить UTC):
```python
from datetime import datetime, timezone
import zoneinfo

def _fmt_ts(iso_utc: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(zoneinfo.ZoneInfo("Asia/Tbilisi")).strftime("%d.%m %H:%M")
    except Exception:
        return iso_utc
```
Применить в рендере журнала и очереди.

---

## Баг 4 (косметика) — нет индикации опроса

Кнопка «Опросить почту» — опрос фоновый, оператор жмёт несколько раз.
Показать `st.info("⏳ Опрос запущен, обновите через ~30 сек")` после нажатия,
или опрашивать GET /v1/agent/status (поле running) и показывать спиннер пока true.

---

## Bump + деплой

Баг 0 — только API. Баг 1 — core (git + --no-cache). Баги 2-4 — core/api/streamlit.

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.17.16: fix move fresh connection, markers BOM/path"
git push origin main

cd C:\work\SignPDFMVPLocal
docker compose build --no-cache api
docker compose build agent streamlit
docker compose up -d --force-recreate
docker compose logs api 2>&1 | Select-Object -First 5
```

Bump: core `__init__.py` + `pyproject.toml` → 1.17.16, api main.py → 1.17.16, CLAUDE.md.

## Тест

1. Прямой sign на кириллическом документе:
```powershell
docker compose exec agent python -c "import httpx,os,json; key=os.environ.get('SIGNFINDER_API_KEY',''); pdf=open('/data/agent/pdfs/originals/29/'+os.listdir('/data/agent/pdfs/originals/29')[0],'rb').read(); a=httpx.post('http://api:8000/v1/analyze',headers={'Authorization':f'Bearer {key}'},files={'file':('c.pdf',pdf,'application/pdf')},timeout=180).json(); anc=a.get('anchors',[]); r=httpx.post('http://api:8000/v1/sign',headers={'Authorization':f'Bearer {key}'},files={'file':('c.pdf',pdf,'application/pdf')},data={'anchors_json':json.dumps(anc),'signer_id':'default','signature_scale':'1.0'},timeout=60); print('sign:', r.status_code, len(r.content), 'bytes')"
```
Ожидаем: `sign: 200 <много> bytes` (раньше было 500 на кириллице).

2. Очистить очередь, снять «прочитано», опросить
3. **Все 5** писем → подписанные PDF (включая кириллические имена)
4. «Подтвердить» → Yellow→Green без 500
5. Лог API без BOM-спама, журнал в местном времени

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
