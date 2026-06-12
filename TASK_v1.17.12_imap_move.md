# SignFinder v1.17.12 — Фикс IMAP move (COPY illegal in state AUTH)

Прочитай `C:\work\CLAUDE.md` перед началом.

---

## Баг

Агент находит письма, обрабатывает, но при раскладке/резолюции падает:
```
500: command COPY illegal in state AUTH, only allowed in states SELECTED
```

## Корень

`signfinder-core/signfinder/intake/imap_source.py`, метод `move()`:

```python
self._imap.select(self._quote(src))   # ← результат НЕ проверяется

try:
    typ, _ = self._imap.uid("move", uid, ...)   # UID MOVE
    if typ == "OK":
        return
except Exception as e:
    logger.debug(...)   # ← после исключения соединение в state AUTH

# Fallback COPY — выполняется БЕЗ повторного SELECT
typ, _ = self._imap.uid("copy", uid, ...)   # ← падает "illegal in state AUTH"
```

Две проблемы:
1. `select()` результат не проверяется — если SELECT не прошёл, COPY идёт в AUTH
2. Когда `UID MOVE` кидает исключение (Gmail сбрасывает соединение в AUTH),
   fallback COPY выполняется без повторного SELECT → падение

## Фикс — переписать метод `move()` в imap_source.py

```python
def move(
    self,
    uid: str,
    dest_folder: str,
    source_folder: str | None = None,
) -> None:
    """Перемещает письмо uid из source_folder в dest_folder."""
    self._connect()
    assert self._imap is not None

    src = source_folder or self._folder_in

    # SELECT source — ОБЯЗАТЕЛЬНО проверять результат, иначе COPY/MOVE падает в AUTH
    typ, _ = self._imap.select(self._quote(src))
    if typ != "OK":
        raise RuntimeError(f"IMAP SELECT {src} failed: {typ}")

    # Попытка UID MOVE (RFC 6851, Gmail поддерживает)
    try:
        typ, _ = self._imap.uid("move", uid, self._quote(dest_folder))
        if typ == "OK":
            logger.debug("UID MOVE %s → %s OK", uid, dest_folder)
            return
    except Exception as e:
        logger.debug("UID MOVE failed (%s), fallback COPY+DELETE", e)
        # После исключения соединение могло сброситься в AUTH —
        # переподключиться и заново SELECT перед COPY
        self._imap = None
        self._connect()
        typ, _ = self._imap.select(self._quote(src))
        if typ != "OK":
            raise RuntimeError(f"IMAP re-SELECT {src} failed: {typ}")

    # Fallback: COPY + DELETE + EXPUNGE
    typ, _ = self._imap.uid("copy", uid, self._quote(dest_folder))
    if typ != "OK":
        raise RuntimeError(f"IMAP COPY {uid} → {dest_folder} failed: {typ}")
    self._imap.uid("store", uid, "+FLAGS", "\\Deleted")
    self._imap.expunge()
    logger.debug("COPY+DELETE %s → %s done", uid, dest_folder)
```

Ключевые изменения:
1. `select()` результат проверяется, при неудаче — RuntimeError с именем папки
2. После исключения UID MOVE — переподключение + повторный SELECT перед COPY
3. COPY результат проверяется

## Также проверить `fetch_raw()` — та же проблема

В `fetch_raw()` тоже `self._imap.select(self._quote(src))` без проверки:
```python
typ, _ = self._imap.select(self._quote(src))
if typ != "OK":
    raise RuntimeError(f"IMAP SELECT {src} failed in fetch_raw: {typ}")
```

## Gmail-нюанс (на заметку)

На Gmail папки = ярлыки. COPY добавляет ярлык назначения, STORE+Deleted+EXPUNGE
убирает исходный ярлык. Для перемещения между SignFinder-ярлыками это работает
корректно. UID MOVE на Gmail тоже поддерживается, но fallback теперь надёжный.

## Bump + деплой (core изменился → git + --no-cache)

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.17.12: fix IMAP move COPY illegal in AUTH state"
git push origin main

cd C:\work\SignPDFMVPLocal
docker compose build --no-cache api
docker compose build agent
docker compose up -d --force-recreate api agent
docker compose logs agent 2>&1 | Select-Object -First 20
```

Bump версии: `signfinder-core/__init__.py` + `pyproject.toml` → 1.17.12

## Тест

1. Положить договор в SignfinderIn → агент опрашивает → раскладка без ошибки COPY
2. В очереди разбора → «Подтвердить» → письмо Yellow → Green без ошибки
3. «Отклонить» → Yellow → Red без ошибки
4. Проверить в Gmail: письмо реально переместилось между ярлыками
5. Оригинал в SignfinderArchive

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
