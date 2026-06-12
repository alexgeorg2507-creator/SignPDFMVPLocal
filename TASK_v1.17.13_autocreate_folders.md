# SignFinder v1.17.13 — Авто-создание IMAP-папок + append не молчит

Прочитай `C:\work\CLAUDE.md` перед началом.

---

## Баг

При «Подтвердить»/«Переподписать»:
```
500: IMAP SELECT SignfinderYellow failed: NO
```

## Корень

1. Ярлык `SignfinderYellow` (и др.) не существует в Gmail. Оператор создал только
   `SignfinderIn` вручную — его хватило для поллинга.
2. `append()` в `imap_source.py` при неудачном APPEND **молча логирует, не падает**:
   ```python
   typ, _ = self._imap.append(...)
   if typ != "OK":
       logger.error(...)   # ← не raise
   ```
   Поэтому при поллинге APPEND в несуществующий SignfinderYellow провалился тихо,
   но письмо попало в очередь. При резолюции SELECT этого ярлыка → NO.

## Фикс — агент сам создаёт недостающие папки

Файл: `signfinder-core/signfinder/intake/imap_source.py`

### 1. Добавить метод `_ensure_folder`

```python
def _ensure_folder(self, folder: str) -> None:
    """Создаёт IMAP-папку/ярлык если не существует. Идемпотентно."""
    assert self._imap is not None
    quoted = self._quote(folder)
    # Проверка существования через SELECT
    typ, _ = self._imap.select(quoted)
    if typ == "OK":
        return  # уже есть
    # Создаём
    typ, data = self._imap.create(quoted)
    if typ != "OK":
        # Gmail может вернуть NO если ярлык уже есть в другом регистре —
        # это не критично, логируем
        logger.warning("IMAP CREATE %s: %s %s", folder, typ, data)
    else:
        logger.info("IMAP CREATE %s OK", folder)
```

### 2. `append()` — создать папку перед APPEND + RAISE при неудаче

```python
def append(self, folder: str, raw_email: bytes) -> None:
    self._connect()
    assert self._imap is not None

    self._ensure_folder(folder)   # ← создать если нет

    date_time = imaplib.Time2Internaldate(time.time())
    typ, data = self._imap.append(self._quote(folder), "\\Seen", date_time, raw_email)
    if typ != "OK":
        raise RuntimeError(f"IMAP APPEND to {folder} failed: {typ} {data}")
    logger.debug("APPEND to %s OK (%d bytes)", folder, len(raw_email))
```

### 3. `move()` — создать dest-папку перед перемещением

В начале `move()`, после `_connect()`:
```python
self._ensure_folder(dest_folder)   # ← гарантировать что назначение есть
```

Затем SELECT source (как в v1.17.12 — с проверкой результата). Если SELECT source
вернул NO (исходной папки нет) — это уже реальная ошибка, raise остаётся.

### 4. Опционально — ensure всех папок при старте поллера

В `poller.py` или `mailbox.py` при первом подключении создать все 5 папок из конфига,
чтобы они гарантированно были до первой обработки:
```python
def ensure_all_folders():
    cfg = load_mail_config()
    src = _get_source()
    for key in ("folder_in", "folder_green", "folder_yellow", "folder_red", "folder_archive"):
        src._ensure_folder(cfg[key])
```
Вызвать один раз в начале `run_one_poll()`.

---

## Gmail-нюанс

`self._imap.create("SignfinderYellow")` создаёт ярлык в Gmail. Если уже есть —
вернёт NO, это не ошибка (ловим в _ensure_folder, не падаем). Ярлыки плоские,
регистр сохраняется.

## Bump + деплой (core → git + --no-cache)

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.17.13: auto-create IMAP folders, append raises on failure"
git push origin main

cd C:\work\SignPDFMVPLocal
docker compose build --no-cache api
docker compose build agent
docker compose up -d --force-recreate api agent
docker compose logs agent 2>&1 | Select-Object -First 20
```

Bump: `signfinder-core/__init__.py` + `pyproject.toml` → 1.17.13

## Тест

1. Удалить в Gmail все ярлыки кроме SignfinderIn (для чистоты теста)
2. Положить договор в SignfinderIn → опросить
3. Агент должен САМ создать недостающие ярлыки (Green/Yellow/Red/Archive)
4. Письмо разложилось, в очереди разбора
5. «Подтвердить» → Yellow→Green без ошибки SELECT
6. Проверить в Gmail: все ярлыки созданы, письма на местах

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
