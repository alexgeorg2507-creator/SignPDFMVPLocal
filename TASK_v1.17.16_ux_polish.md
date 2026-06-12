# SignFinder v1.17.16 — Маркер auth + время + версия + прогресс опроса + переподписать

Прочитай `C:\work\CLAUDE.md` перед началом.

Статус: подпись работает end-to-end (кириллица побеждена в 1.17.15). Это блок
доводки UX + один баг авторизации.

---

## Баг 1 — «Not authenticated» при сохранении режима маркера

### Корень

`SignPDFMVPLocal/streamlit/pages/4_Nastroyki.py`, таб «Подписант» → «Режим простановки».
Два запроса к sign-mode идут БЕЗ заголовка авторизации:

```python
r = requests.get(f"{API_BASE}/v1/settings/sign-mode", timeout=5)          # нет headers!
r = requests.put(f"{API_BASE}/v1/settings/sign-mode", json={...}, timeout=5)  # нет headers!
```

А API (`/v1/settings/sign-mode`) требует `ApiKeyDep`. Без Bearer → 401 "Not authenticated".

### Фикс

Добавить `headers=_api_headers()` в оба запроса:
```python
r = requests.get(f"{API_BASE}/v1/settings/sign-mode", headers=_api_headers(), timeout=5)
...
r = requests.put(f"{API_BASE}/v1/settings/sign-mode",
                 json={"use_signature": use_sig, "use_marker": use_mrk, "marker_color": marker_color},
                 headers=_api_headers(), timeout=5)
```

### Заодно — проверить весь файл на запросы без headers

В табе LLM тоже запросы без headers (`_fetch_llm_config`, `_save_llm_config`,
`_test_llm_provider` — `requests.get/post` к `/v1/config/llm*` без `headers=`).
Сейчас работают (видимо llm_config роутер без ApiKeyDep), но это непоследовательно
и хрупко. Добавить `headers=_api_headers()` во ВСЕ запросы к API в этом файле
для единообразия. Проверить grep'ом:
```powershell
Select-String "requests\.(get|post|put|patch|delete)" 4_Nastroyki.py
```
Каждый вызов к `/v1/...` должен иметь `headers=_api_headers()` (кроме `/health`,
`/v1/version` — они публичные).

---

## Баг 2 — время в журнале UTC → местное (Asia/Tbilisi, UTC+4)

Журнал агента хранит UTC (правильно), Streamlit показывает UTC. Конвертировать
при отображении.

Файл: страница агента (`6_Agent_Mail.py` или как называется) — вкладка «Журнал»
и «Очередь». Добавить хелпер и применить к колонке времени:

```python
from datetime import datetime, timezone
try:
    import zoneinfo
    _TZ = zoneinfo.ZoneInfo("Asia/Tbilisi")
except Exception:
    _TZ = timezone.utc

def _fmt_local(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_TZ).strftime("%d.%m %H:%M")
    except Exception:
        return iso_str
```

Применить везде где показывается `ts` / `received_at` (журнал, очередь).
Хранение оставить UTC — конвертация только на отображении.

---

## Баг 3 — версия в футере непоследовательная

Футер показывает `SignFinder v1.17.15` при core 1.17.16. Источник версии разный
на разных страницах: где-то `/v1/version` (api_version), где-то `/health`
(core_version), где-то хардкод.

### Фикс — единый источник

Все футеры/подписи версий берут из `GET /v1/version` → `api_version`.
Убедиться что endpoint `/v1/version` возвращает АКТУАЛЬНУЮ версию (читает из
`signfinder.__version__` или из main.py — единый источник).

Проверить во ВСЕХ страницах Streamlit (`pages/*.py`):
- заменить хардкод `v1.17.x` и вызовы `/health core_version` на единый `_sf_version()`
  из `/v1/version`
- `6_Agent_Mail.py` показывает «SignFinder v?» — тоже подключить `_sf_version()`

Главное: одна функция `_sf_version()`, один источник `/v1/version`, везде одинаково.

---

## Баг 4 — индикация прогресса опроса почты

Кнопка «Опросить почту сейчас» — опрос фоновый, результат не сразу, оператор
жмёт несколько раз.

Файл: `6_Agent_Mail.py`.

После нажатия:
1. Вызвать POST `/v1/agent/poll-now`
2. Показать `st.info("⏳ Опрос запущен. Письма появятся в журнале по мере обработки.")`
3. Опрашивать GET `/v1/agent/status` — если `running: true`, показать спиннер/бейдж
   «🔄 Идёт опрос…», если false и last_poll свежий — «✅ Опрос завершён»
4. Кнопку «Обновить» рядом — перечитать журнал/очередь

Минимально: после poll-now показать постоянный баннер «опрос идёт в фоне, нажмите
Обновить через ~30 сек» + автоindicator по полю running из status. Не блокировать UI.

---

## Баг 5 — «Переподписать»: что делает + доделать UI

Кнопка «Скачать / Переподписать» в очереди разбора. Логика resign в
`agent/app/mailbox.py do_resolve(action="resign")`: пересоздаёт подписанный PDF
по НОВЫМ якорям (`new_anchors`) и кладёт в Green.

### Проблема

UI не даёт оператору задать новые якоря — кнопка либо шлёт resign без анкеров
(тогда что переподписывать?), либо непонятно что делает.

### Что сделать (выбрать по месту)

Вариант A (минимальный, для MVP): переименовать в «📥 Скачать подписанный» —
просто отдать уже подписанный PDF на скачивание оператору. Без переподписания.

Вариант B (полный): раскрыть панель с превью PDF + возможностью кликнуть новые
места подписи (как в Авто-подписании) → собрать new_anchors → resign.

Для MVP рекомендую **A** — скачивание готового PDF. Переподписание с ручной
разметкой (B) отложить, это отдельная большая UI-задача (переиспользование
streamlit-image-coordinates из 5_Avto_podpisanie).

Уточни у архитектора какой вариант. По умолчанию делай A.

---

## Bump + деплой (всё в UI/API, core не трогаем кроме версии)

```powershell
cd C:\work\SignPDFMVPLocal
docker compose build streamlit api
docker compose up -d --force-recreate streamlit api
```

Версия → 1.17.16 в main.py + CLAUDE.md. (Если /v1/version читает core
`__version__` — убедись что он 1.17.16, тогда нужен и core bump + git push.)

## Тест

1. Настройки → Подписант → Режим простановки → отметить маркер → «Сохранить режим» → БЕЗ ошибки auth
2. Журнал агента — время местное (UTC+4, совпадает с часами)
3. Все страницы показывают одну версию (1.17.16)
4. «Опросить почту» → видна индикация «идёт опрос», не нужно жать повторно
5. Очередь разбора → «Скачать» отдаёт подписанный PDF

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
