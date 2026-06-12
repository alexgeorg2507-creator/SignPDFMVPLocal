# SignFinder v1.17.7 — Структурные паттерны в конфиг + масштаб в шаблоне

Прочитай `C:\work\CLAUDE.md` перед началом.

---

## Контекст (зачем)

Закрываем TD-07. Цель: при смене LLM-провайдера поиск подписи/сторон/синонимов
правится ТОЛЬКО промптом. Для этого структурную конвенцию подписи `____ (ФИО)`
выносим из pipeline-кода в детерминированный markers-конфиг.

**Архитектурный принцип:**
- Стабильная конвенция (`____ (...)`, `Заказчик___`) → markers-конфиг, детерминированно, не зависит от модели
- Специфика документа (наша сторона, юрлицо, синонимы) → LLM + промпт

После фикса смена модели затрагивает только LLM-слой (промпт), структурные
паттерны работают всегда одинаково на любом провайдере.

---

## Задача 1 — Структурный паттерн подписи → markers

### 1.1 Добавить в MARKERS_DEFAULTS (signfinder-core/signfinder/pipeline/settings.py)

В каждый язык добавить ключ `signature_block_patterns`:

```python
"ru": {
    "underline_patterns": ["_{3,}", "\\.{5,}"],
    "marker_words": [...],
    "section_anchors": [...],
    "signature_block_patterns": ["_{3,}\\s*\\([^)]{3,40}\\)"],
},
"en": {
    ...
    "signature_block_patterns": ["_{3,}\\s*\\([^)]{3,40}\\)"],
},
"pl": {
    ...
    "signature_block_patterns": ["_{3,}\\s*\\([^)]{3,40}\\)"],
},
```

Паттерн name-independent (вариант «б»): матчит `____ (что угодно 3-40 симв)`.
Не зависит от того, какой вариант имени/синонима в скобках.

### 1.2 Убрать хардкод из auto1.py

Удалить функцию `_signer_initials_pattern` целиком.

Удалить блок её вызова в `run_pipeline_auto_1` (после step4):
```python
# УДАЛИТЬ ЭТОТ БЛОК:
_synth = _signer_initials_pattern(our_side.get("signer", ""))
if _synth:
    ...
    patterns.append(_synth)
```

### 1.3 Добавить структурные паттерны из markers — ПЕРВЫМ слоем

В `run_pipeline_auto_1`, ДО или сразу после step4, добавить структурные
паттерны из markers в общий пул паттернов:

```python
# Структурные паттерны подписи — детерминированные, из markers-конфига.
# Не зависят от LLM, работают на любом провайдере.
markers_block = get_markers_for_language(storage, language)
structural = markers_block.get("signature_block_patterns", [])
for sp in structural:
    try:
        re.compile(sp, re.IGNORECASE | re.UNICODE)
        if sp not in patterns:
            patterns.append(sp)
    except re.error:
        sys.stderr.write(f"[auto1] bad structural pattern '{sp}'\n")
```

**Логика «всегда первым»:** структурные паттерны идут в пул всегда, независимо
от того что вернул LLM. LLM (step4) добавляет специфику документа сверху.

### 1.4 Ours/theirs — без изменений

Паттерн `____ (...)` матчит блоки подписи ОБЕИХ сторон. Определение «наша/чужая»
остаётся в `find_signatures` (step5) через aliases/other_aliases — как сейчас.
НЕ менять эту логику. Если оверматч — режется на dedup в Streamlit (TD-08).

Проверь `signfinder/anchors/finder.py` `find_signatures` чтобы убедиться что
структурный паттерн корректно проходит через aliasing.

---

## Задача 2 — Масштаб подписи в шаблоне

### 2.1 Модель DocumentTemplate (signfinder-core/signfinder/templates/models.py)

Добавить поле:
```python
@dataclass
class DocumentTemplate:
    ...
    synonyms_used: dict
    signature_scale: float = 1.0    # НОВОЕ: масштаб подписи (1.0 = 42pt)
    usage_stats: dict = field(...)
```

Default 1.0 — обратная совместимость со старыми шаблонами (нет поля → 1.0).

### 2.2 save_pipeline_template (auto1.py) — принять и сохранить scale

```python
def save_pipeline_template(
    doc, language, our_side, anchors, storage,
    template_name=None,
    signature_scale: float = 1.0,    # НОВОЕ
) -> str:
    ...
    tpl = new_template(...)
    tpl.signature_scale = signature_scale
    ...
```

Проверь `new_template` в `templates/storage.py` — возможно тоже надо прокинуть.

### 2.3 API — сохранение шаблона с scale

В роутере templates.py (POST /v1/templates) — принять signature_scale из payload,
прокинуть в save. GET /v1/templates/{id} — вернуть signature_scale.

### 2.4 Streamlit — сохранять текущий scale при создании шаблона

В `5_Avto_podpisanie.py` `_save_template()`: добавить в payload
`"signature_scale": st.session_state.get("sig_scale_slider", 1.0)`.

### 2.5 Зелёный путь — применять scale из шаблона

При green-матче (apply_template): прочитать `template.signature_scale`,
установить как дефолт слайдера `sig_scale_slider`. Слайдер может переопределить
в текущей сессии (дефолт из шаблона, оператор крутит если надо).

В UI где грузится шаблон по зелёному:
```python
st.session_state["sig_scale_slider"] = matched_template.get("signature_scale", 1.0)
```

---

## Bump версий

- `signfinder-core/__init__.py` + `pyproject.toml`: `1.17.7`
- `signfinder-api/app/main.py`: `1.17.7`
- `C:\work\CLAUDE.md`: `Текущая версия: 1.17.7`

## Деплой (PowerShell — отдельными строками)

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.17.7: structural patterns to markers config, template signature_scale"
git push origin main

cd C:\work\SignPDFMVPLocal
docker compose build --no-cache api
docker compose build streamlit
docker compose up -d --force-recreate
docker compose logs api 2>&1 | Select-Object -First 10
```

## Тест

1. На DeepSeek прогнать документ → подпись `____ (ФИО)` находится (структурный паттерн, не LLM)
2. Переключить на Anthropic → тот же результат (паттерн детерминированный)
3. Авто-подписание → подвинуть слайдер масштаба → сохранить шаблон
4. Загрузить документ того же типа → зелёный → масштаб = из шаблона
5. Проверить старый шаблон (без signature_scale) → применяется с 1.0, не падает

## Обновить TECH_DEBT.md

TD-07 → пометить закрытым в v1.17.7. TD-08 (dedup в Streamlit) остаётся.

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
**ОБНОВЛЁННЫЕ:** ссылка + путь. **НОВЫЕ:** ссылка + путь.
