# SignFinder v1.17.14 — Фикс IMAP abort (Gmail SELECT desync) + poll-now фон

Прочитай `C:\work\CLAUDE.md` перед началом.

---

## Баг

После того как агент находит и обрабатывает письма, при раскладке падает:
```
imaplib.IMAP4.abort: command: SELECT => unexpected response: b'1] Predicted next UID.'
```
Письма приходят пустые (без вложений), потому что append/move падают.

## Корень

Файл `signfinder-core/signfinder/intake/imap_source.py`.

Две причины:
1. `_ensure_folder` проверяет существование папки через `SELECT`. Gmail на SELECT
   отдаёт `* OK [UIDNEXT 1] Predicted next UID.` — imaplib спотыкается на хвосте.
2. Рассинхрон буфера: `poll()` делает `FETCH` больших писем и оставляет недочитанный
   хвост в сокете. Следующий `SELECT` (в `_ensure_folder` при append) читает чужой
   хвост → `abort`.

---

## Фикс 1 — `_ensure_folder` без SELECT (только CREATE)

`SELECT` — неправильный способ проверки существования папки (меняет состояние +
многословный ответ Gmail). Заменить на CREATE напрямую: если папка есть, Gmail
вернёт NO — это нормально, игнорируем.

```python
def _ensure_folder(self, folder: str) -> None:
    """Создаёт IMAP-папку/ярлык если не существует. Идемпотентно.
    БЕЗ SELECT — SELECT на Gmail даёт многословный ответ и ломает парсер imaplib.
    """
    assert self._imap is not None
    quoted = self._quote(folder)
    try:
        typ, data = self._imap.create(quoted)
        if typ == "OK":
            logger.info("IMAP CREATE %s OK", folder)
        else:
            # NO = папка/ярлык уже существует — это норма, не ошибка
            logger.debug("IMAP CREATE %s: %s (вероятно уже есть)", folder, typ)
    except Exception as e:
        # CREATE существующей папки может кинуть — не критично
        logger.debug("IMAP CREATE %s exception: %s (вероятно уже есть)", folder, e)
```

## Фикс 2 — `poll()` закрывает соединение после чтения

Чтобы рассинхрон от FETCH не утёк в фазу записи (append/move), закрыть соединение
в конце `poll()`. Письма уже в памяти. Фаза записи получит свежее соединение.

В конце метода `poll()`, ПЕРЕД `return messages`:
```python
        # Закрыть соединение после чтения — FETCH больших писем оставляет
        # рассинхрон в буфере, который ломает последующие SELECT (Gmail).
        # append/move получат свежее соединение через _connect().
        self.close()

        return messages
```

После этого `append()`/`move()` вызовут `_connect()`, который создаст новое
соединение (noop на закрытом упадёт → реконнект).

## Фикс 3 — порядок в `append()`: ensure ПОСЛЕ connect, без SELECT-зависимости

`append()` уже вызывает `_connect()` и `_ensure_folder()`. После фикса 1
`_ensure_folder` не делает SELECT — APPEND работает в state AUTH, всё ок.
Проверь что порядок: `_connect()` → `_ensure_folder()` → `append()`. Не менять.

## Фикс 4 — `move()`: ensure_folder dest без SELECT

`move()` вызывает `_ensure_folder(dest_folder)` (теперь без SELECT — ок), потом
`SELECT src` (это на свежем соединении после фикса 2 — парсится нормально).
Логику move не трогать, она корректна после фикса 1+2.

---

## Фикс 5 (агент) — poll-now в фоне, чтобы не было таймаута 30с

Файл `SignPDFMVPLocal/agent/app/main.py`.

Сейчас `/poll-now` обрабатывает все письма синхронно перед ответом. Прокси
(Streamlit→api→agent) имеет таймаут 30с → отваливается на тяжёлых письмах.
Хотя агент в фоне дорабатывает, UI показывает ошибку таймаута.

Переделать `/poll-now` на запуск в фоне с немедленным ответом:

```python
@app.post("/poll-now")
async def poll_now():
    from app.config import load_mail_config
    if not load_mail_config()["imap_host"]:
        raise HTTPException(status_code=503, detail="IMAP не настроен")
    from app.poller import get_poller_state, run_one_poll
    if get_poller_state().get("running"):
        return {"status": "already_running"}
    # Запустить опрос в фоне, не ждать завершения
    asyncio.get_event_loop().run_in_executor(None, run_one_poll)
    return {"status": "started"}
```

UI после нажатия покажет «опрос запущен», результаты появятся в очереди/журнале
по мере обработки (оператор обновляет страницу). Это нормально.

---

## Bump + деплой (core → git + --no-cache)

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.17.14: fix IMAP abort (ensure_folder without SELECT, poll closes connection)"
git push origin main

cd C:\work\SignPDFMVPLocal
docker compose build --no-cache api agent
docker compose up -d --force-recreate api agent
docker compose logs agent 2>&1 | Select-Object -First 10
```

Bump: `signfinder-core/__init__.py` + `pyproject.toml` → 1.17.14.
Agent `main.py` version string → 1.17.14.

## Тест

1. Снять «прочитано» с писем в SignfinderIn (или прислать новые)
2. Агент Mail → «Опросить почту сейчас» → UI сразу показывает «запущен», без таймаута
3. Обновить страницу через ~30с → письма в очереди
4. Проверить логи: `docker compose logs agent 2>&1 | Select-String "abort|CREATE|APPEND"` — НЕТ abort
5. В Gmail SignfinderYellow → письмо с **подписанным PDF** во вложении (не пустое, не docx)
6. «Подтвердить» → Yellow→Green без ошибок

---

## Если abort останется

Значит рассинхрон глубже — тогда добавить принудительный реконнект в начале
`append()` и `move()`:
```python
def _reconnect(self):
    if self._imap is not None:
        try: self._imap.logout()
        except Exception: pass
        self._imap = None
    self._connect()
```
Но сначала пробуем фикс 1+2 — закрытие после poll должно решить.

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
