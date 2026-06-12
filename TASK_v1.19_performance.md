# SignFinder v1.19.0 — Оптимизация производительности

Прочитай `C:\work\CLAUDE.md` и `C:\work\signfinder-core\PERFORMANCE_ANALYSIS_v1.18.md`
перед началом.
Изменения в signfinder-core: pdf/parser.py, pdf/language.py, signfinder/__init__.py,
pipeline/settings.py.
Деплой: --no-cache rebuild всех сервисов.

ОБЯЗАТЕЛЬНО: тайминги — сначала. Делать по шагам, замерять после каждого.
Регрессия по функционалу недопустима.

---

## ШАГ 1 — Тайминги в pipeline_debug (ИЗМЕРЯЕМ ЧТО ЕСТЬ)

Добавить тайминги в `signfinder/__init__.py::SignFinder.analyze()`.
Используем `time.perf_counter()`.

```python
import time

def analyze(self, pdf_bytes, language=None, filename="document.pdf") -> AnalysisResult:
    t0 = time.perf_counter()
    timings = {}

    # ... существующие проверки ...

    t_parse = time.perf_counter()
    doc = parse_pdf_bytes(pdf_bytes, filename=filename)
    timings["parse_ms"] = int((time.perf_counter() - t_parse) * 1000)
    timings["langdetect_calls"] = getattr(doc, "_langdetect_calls", 0)

    t_lang = time.perf_counter()
    lang = language or detect_language(doc, llm=self.llm)
    if not lang or lang == "unknown":
        lang = "ru"
    timings["detect_lang_ms"] = int((time.perf_counter() - t_lang) * 1000)
    timings["detect_lang_llm_used"] = timings["detect_lang_ms"] > 200  # LLM = медленно

    # ... fingerprint / matcher ...
    t_matcher = time.perf_counter()
    fp = compute_fingerprint(fitz_doc, lang)
    matcher = find_matching_templates(...)
    timings["matcher_ms"] = int((time.perf_counter() - t_matcher) * 1000)

    # Шаблонный путь — тайминг total
    if matcher.traffic_light == "green" and matcher.best_match:
        timings["total_ms"] = int((time.perf_counter() - t0) * 1000)
        timings["path"] = "template"
        result = AnalysisResult(...)
        result.pipeline_debug["timings_ms"] = timings
        return result

    # Полный пайплайн
    t_pipeline = time.perf_counter()
    pipeline = run_pipeline_auto_1(...)
    timings["pipeline_ms"] = int((time.perf_counter() - t_pipeline) * 1000)
    timings["total_ms"] = int((time.perf_counter() - t0) * 1000)
    timings["path"] = "pipeline"

    result = AnalysisResult(...)
    result.pipeline_debug["timings_ms"] = timings
    # Объединить с debug из pipeline
    result.pipeline_debug.update(pipeline.debug)
    result.pipeline_debug["timings_ms"] = timings
    return result
```

Счётчик langdetect в parser.py — добавить поле в ParsedDocument:
```python
@dataclass
class ParsedDocument:
    ...
    _langdetect_calls: int = 0  # служебное поле для профилирования
```
И инкрементировать при каждом вызове `detect()`.

После деплоя — прогнать 6 PL/MK документов пакетом, посмотреть
`pipeline_debug.timings_ms` в каждом debug JSON. Записать базовые цифры.

---

## ШАГ 2 — Убрать LLM из шаблонного пути (ГЛАВНАЯ ПРОБЛЕМА)

### Что происходит сейчас

В `analyze()`:
```python
lang = language or detect_language(doc, llm=self.llm)
```

`detect_language(doc, llm=self.llm)` вызывается ДО matcher. Если langdetect
вернул `bg`/`hr`/`sl` (каша mk+en) — уходит в `_llm_detect()` — 2-3 секунды.
Это происходит ДАЖЕ для шаблонного пути (где LLM не нужен вообще).

### Фикс: разделить быстрый и точный detect

В `pdf/language.py` добавить быструю версию без LLM:

```python
def detect_language_fast(doc) -> str:
    """Быстрая детекция БЕЗ LLM. Для шаблонного пути.

    Возвращает поддерживаемый код если langdetect его распознал,
    иначе — что бы langdetect ни вернул (bg, hr...) — возвращаем как есть.
    Для matcher язык нужен только как метка (fingerprint), точность не критична.
    """
    parser_lang = (getattr(doc, "language", "") or "").lower()[:2]
    return parser_lang if parser_lang else "unknown"
```

В `signfinder/__init__.py::analyze()` изменить порядок:

```python
# БЫСТРАЯ детекция — для matcher достаточно языковой метки
lang_fast = language or detect_language_fast(doc)
if not lang_fast or lang_fast == "unknown":
    lang_fast = "ru"

# fingerprint + matcher работают на lang_fast (не нужна LLM-точность)
fp = compute_fingerprint(fitz_doc, lang_fast)
matcher = find_matching_templates(fitz_doc, lang_fast, storage=self.storage, fingerprint=fp)

# ШАБЛОННЫЙ ПУТЬ: выходим БЕЗ LLM-вызова detect_language
if matcher.traffic_light == "green" and matcher.best_match:
    tpl = load_template(self.storage, matcher.best_match.template_id)
    if tpl is not None:
        ...
        return AnalysisResult(traffic_light="green", ...)  # ← LLM не вызывался

# ТОЛЬКО для полного пайплайна — точная детекция с LLM fallback при необходимости
lang = language or detect_language(doc, llm=self.llm)
if not lang or lang == "unknown":
    lang = lang_fast  # fallback на быстрый результат, не на "ru"

pipeline = run_pipeline_auto_1(doc=doc, language=lang, ...)
```

ВАЖНО: шаблонному пути нужен lang только для fingerprint (поле в FingerprintData)
и для find_matching_templates. Матчинг идёт по simhash/jaccard/cosine — не по языку.
Язык в fingerprint — это метаданные для фильтрации, а не ключ матчинга.
Если matcher нашёл шаблон с lang="bg" и исходный шаблон был lang="mk" — они
матчатся по fingerprint, не по строке языка. Безопасно.

Ожидаемый выигрыш: шаблонный путь -2.5 с (LLM-вызов исчезает полностью).

---

## ШАГ 3 — Кэш langdetect в parse_pdf_bytes

### Что происходит сейчас

В `pdf/parser.py::parse_pdf_bytes()`, в цикле по страницам:
```python
if gutter:
    # для КАЖДОЙ dual-страницы:
    lang_left = detect(left_text[:500])
    lang_right = detect(right_text[:500])
```

Agreement (6 стр, все dual) = 12 вызовов langdetect + 1 финальный = 13.
Первый вызов langdetect в процессе — ленивая загрузка профилей (~300-500 мс).

### Фикс: кэшировать языки колонок

```python
# В parse_pdf_bytes, ДО цикла:
cached_col_langs: tuple[str, str] | None = None
langdetect_call_count = 0

# В цикле, в ветке if gutter:
if cached_col_langs is None:
    # Первая dual-страница — детектируем
    try:
        ll = _detect_safe(left_text[:500])
        lr = _detect_safe(right_text[:500])
        cached_col_langs = (ll, lr)
        langdetect_call_count += 2
    except Exception:
        cached_col_langs = ("unknown", "unknown")
lang_left, lang_right = cached_col_langs
```

Добавить хелпер:
```python
def _detect_safe(text: str) -> str:
    try:
        from langdetect import detect
        return detect(text) if text.strip() else "unknown"
    except Exception:
        return "unknown"
```

Для финального языка документа (по full_text) — один вызов как и был.

Итог: Agreement 13 вызовов → 3 (2 для первой dual-страницы + 1 финальный).

---

## ШАГ 4 — Кэш markers/profile per-analyze (TTL 60 сек)

В `pipeline/settings.py` сейчас `get_markers_for_language()` и
`load_signer_profile_by_id()` читают JSON с диска при каждом вызове.
За один пайплайн это 3-5 чтений одного файла.

Добавить модульный кэш с TTL:

```python
import time as _time
_CACHE: dict[str, tuple[float, Any]] = {}
_TTL = 60.0  # секунды


def _cached(key: str, loader, *args):
    """Кэш с TTL=60с. key должен включать все параметры влияющие на результат."""
    now = _time.monotonic()
    if key in _CACHE and now - _CACHE[key][0] < _TTL:
        return _CACHE[key][1]
    result = loader(*args)
    _CACHE[key] = (now, result)
    return result
```

Применить к `load_markers` и `load_signer_profile_by_id`:

```python
def get_markers_for_language(storage, language: str) -> dict:
    def _load():
        # ... существующий код ...
    return _cached(f"markers:{language}", _load)


def load_signer_profile_by_id(storage, signer_id: str) -> dict:
    def _load():
        # ... существующий код ...
    return _cached(f"profile:{signer_id}", _load)
```

ВАЖНО: TTL=60с означает что изменения через UI применятся максимум через 60 сек.
Это приемлемо. Если нужно немедленно — `_CACHE.clear()` после PUT-запроса
в соответствующем API-роутере (необязательно, можно оставить TTL).

---

## ШАГ 5 — Ограничить step4 паттерны

В `pipeline/auto1.py`, в функции step4 или в вызове format_generate_regex,
добавить в промпт явное ограничение числа паттернов.

В `signfinder/prompts/regex_generation.py` (или где format_generate_regex):
найти строку формирующую промпт и добавить:

```
ВАЖНО: верни НЕ БОЛЕЕ 15 паттернов — только наиболее характерные для
ЭТОГО конкретного документа. Не генерируй декартово произведение всех
вариантов подчёркиваний × все маркеры. Предпочти 1-2 точных паттерна
10 похожим.
```

И детерминированный постфильтр после получения паттернов от LLM:

```python
def _deduplicate_patterns(patterns: list[str], max_count: int = 20) -> list[str]:
    """Убрать семантические дубли и ограничить число паттернов."""
    seen_normalized = set()
    result = []
    for p in patterns:
        # Нормализация: убрать пробелы, нижний регистр для сравнения
        norm = re.sub(r'\s+', '', p.lower())
        if norm not in seen_normalized:
            seen_normalized.add(norm)
            result.append(p)
        if len(result) >= max_count:
            break
    return result
```

Вызвать после получения final_patterns в run_pipeline_auto_1:
```python
final_patterns = _deduplicate_patterns(final_patterns, max_count=20)
```

---

## Bump + деплой

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.19.0: performance — no LLM in template path, langdetect cache, marker/profile cache"
git push origin main

cd C:\work\SignPDFMVPLocal
docker compose build --no-cache
docker compose up -d --force-recreate
docker compose logs api 2>&1 | Select-String "Core v"
```

Bump: core `__init__.py` → 1.19.0, `pyproject.toml` → 1.19.0, CLAUDE.md.

---

## Целевые показатели (из PERFORMANCE_ANALYSIS_v1.18.md)

| Сценарий | Текущее | Цель |
|----------|---------|------|
| Шаблонный путь (1-4 стр) | 3700-4800 мс | ≤ 1500 мс |
| Шаблонный путь (Amendment dup) | 4777 мс | ≤ 1200 мс |
| Полный анализ (yellow) | ~15 с | ≤ 10 с |

---

## Контроль регрессии

После каждого шага — прогон 6 PL/MK + 5 RU через пакетную обработку.
В debug JSON смотреть `timings_ms`:

```json
{
  "timings_ms": {
    "parse_ms": 250,
    "detect_lang_ms": 5,          ← после Шага 2: не 2500
    "detect_lang_llm_used": false, ← для шаблонного пути
    "matcher_ms": 600,
    "pipeline_ms": 8000,           ← только для yellow
    "total_ms": 1200,              ← шаблонный путь
    "langdetect_calls": 3,         ← после Шага 3: не 13
    "path": "template"
  }
}
```

Если регрессия по функционалу (шаблон не применяется, подписи уехали) —
откат через git revert, разбираем точечно.

---

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
Шаги строго по порядку: 1 (тайминги) → замерить → 2 → замерить → 3 → ... →
Не делать всё разом.
