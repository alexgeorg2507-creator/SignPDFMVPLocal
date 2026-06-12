# SignFinder v1.18.2 — UX очереди: «В разбор» + дружелюбный timeout

Прочитай `C:\work\CLAUDE.md` перед началом.
Все изменения только в одном файле: `SignPDFMVPLocal/streamlit/pages/6_Agent_Mail.py`

---

## Фикс 1 — Дружелюбный timeout вместо страшного HTTPConnectionPool

### Симптом

Иногда появляется: «Агент недоступен: HTTPConnectionPool(host='api', port=8000):
Read timed out. (read timeout=5)»

### Причина

`_api_get` ловит все исключения через `except Exception as e: return {"error": str(e)}`.
При timeout `requests` кидает `requests.exceptions.Timeout` — длинная техническая
строка попадает в сообщение оператору. Агент при этом работает нормально — просто
api был занят LLM-вызовом (~10-30с) и не успел ответить на статус-запрос за 5с.

### Фикс — ловить timeout отдельно

В функции `_api_get` добавить перехват `Timeout` ДО общего `except Exception`:

```python
def _api_get(path: str) -> dict:
    client = get_api_client()
    try:
        r = requests.get(f"{API_BASE}{path}",
                         headers={"Authorization": f"Bearer {client.api_key}"}, timeout=5)
        return r.json() if r.ok else {"error": f"{r.status_code}"}
    except requests.exceptions.Timeout:
        return {"_timeout": True}          # ← отдельный ключ, не "error"
    except Exception as e:
        return {"error": str(e)}
```

В блоке показа статуса добавить обработку `_timeout`:

```python
status = _api_get("/v1/agent/status")
if status.get("_timeout"):
    st.info("⏳ API занят — возможно идёт обработка писем. Нажмите «Обновить» через ~30 сек.")
elif status.get("error"):
    st.warning(f"Агент недоступен: {status['error']}")
else:
    # ... нормальный показ метрик (как сейчас)
```

Никакого «HTTPConnectionPool» оператор больше не видит.

---

## Фикс 2 — Кнопка «✏️ В разбор» рядом с «Загрузить»

### Что сейчас

В экспандере «Скачать / Переподписать»:
1. Нажать «📥 Загрузить» → загружается data (signed PDFs + оригиналы)
2. Потом нажать «✏️ {имя файла}» → `_send_to_razbor` → переход на страницу 5

Два клика, неочевидный флоу.

### Что нужно

Рядом с «Загрузить» добавить кнопку «✏️ В разбор» — один клик:
1. Загружает данные из API
2. Сразу вызывает `_send_to_razbor` для первого оригинального PDF
3. Переходит на страницу 5 (Авто-подписание)

Оператор там: видит PDF, может кликнуть новые места подписи, сохранить шаблон.

### Реализация

Внутри экспандера заменить одиночную кнопку «Загрузить» на две в колонках:

```python
with st.expander("✏️ Скачать / Переподписать"):
    col_load, col_razbor = st.columns(2)

    with col_load:
        if st.button("📥 Загрузить", key=f"load_{uid}", use_container_width=True):
            st.session_state[f"_loaded_{uid}"] = _api_get(f"/v1/agent/queue/{uid}")

    with col_razbor:
        if st.button("✏️ В разбор", key=f"razbor_{uid}", use_container_width=True):
            data = _api_get(f"/v1/agent/queue/{uid}")
            originals = data.get("original_pdfs", [])
            if originals:
                # Берём первый оригинал (обычно 1 PDF в письме)
                _send_to_razbor(uid, originals[0], data.get("item", item))
            else:
                st.warning("⚠️ Оригиналы недоступны (старое письмо).")

    # Данные после «Загрузить» (как раньше)
    data = st.session_state.get(f"_loaded_{uid}")
    if data:
        for sp in data.get("signed_pdfs", []):
            st.download_button(
                f"💾 {sp['name']}", data=base64.b64decode(sp["b64"]),
                file_name=sp["name"], mime="application/pdf",
                key=f"dl_{uid}_{sp['name']}")

        st.caption("Переразметить и переподписать вручную:")
        for orig in data.get("original_pdfs", []):
            if st.button(f"✏️ {orig['name']}", key=f"resign_{uid}_{orig['name']}",
                         use_container_width=True):
                _send_to_razbor(uid, orig, data.get("item", {}))
        if not data.get("original_pdfs"):
            st.caption("⚠️ Оригиналы недоступны (старое письмо).")
```

Если в письме несколько PDF — «В разбор» берёт первый. Остальные
доступны через «Загрузить» → «✏️ имя файла» (старый путь остаётся).

---

## Деплой (только streamlit — core/api не трогаем)

```powershell
cd C:\work\SignPDFMVPLocal
docker compose build streamlit
docker compose up -d --force-recreate streamlit
```

## Тест

1. Очередь → письмо → экспандер «Скачать / Переподписать»:
   - видны ДВЕ кнопки: «📥 Загрузить» и «✏️ В разбор»
2. Нажать «✏️ В разбор» → открывается страница «Авто-подписание» с PDF
3. На странице Авто-подписание: видны места подписи, можно кликнуть новые,
   сохранить шаблон → теперь следующий такой договор пойдёт в Green автоматически
4. Когда api занят обработкой → «⏳ API занят — возможно идёт обработка писем...»
   вместо страшного HTTPConnectionPool

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
