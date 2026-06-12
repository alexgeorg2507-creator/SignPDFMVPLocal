# SignFinder v1.19 — Оптимизация производительности

Прочитай `C:\work\CLAUDE.md` и `C:\work\signfinder-core\PERFORMANCE_ANALYSIS_v1.18.md`
перед началом.

Изменения только в signfinder-core. Деплой: --no-cache rebuild api.

ВАЖНО: эта версия НЕ меняет функционал, только производительность. Регрессия не
допустима. После каждой правки — прогон тестового корпуса (русский + PL/MK).

---

## Цель

| Сценарий | Текущее | Цель v1.19 |
|----------|---------|-----------|
| Применение шаблона | 3700-4800 мс | ≤ 1500 мс |
| Полный анализ (yellow) | ~15 с | ≤ 10 с |

Возвращаемся к baseline v1.16, не теряя dual-column и multi-signer.

---

## ШАГ 1 — Тайминги в pipeline_debug (СНАЧАЛА, для измерений)

Прежде чем оптимизировать — добавить тайминги, чтобы видеть что РЕАЛЬНО медленное,
а не строить догадки.

В `signfinder/__init__.py::analyze()` и `pipeline/auto1.py::run_pipeline_auto_1()`
обернуть ключевые шаги в `time.perf_counter()`:

```python
import time

class _Timer:
    def __init__(self):
        self.t0 = time.perf_counter()
        self.spans: dict = {}
        self._marks: dict = {}

    def mark(self, name: str) -> None:
        self._marks[name] = time.perf_counter()

    def stop(self, name: str) -> None:
        if name in self._marks:
            self.spans[f"{name}_ms"] = int((time.perf_counter() - self._marks[name]) * 1000)

    def total_ms(self) -> int:
        return int((time.perf_counter() - self.t0) * 1000)
```

В analyze() обернуть:
- parse_pdf_bytes
- detect_language
- compute_fingerprint
- find_matching_templates
- detect_signer_profile
- run_pipeline_auto_1 (целиком + внутри step3/step4/step5)

Результат класть в `pipeline_debug["timings_ms"]` (если pipeline ran) или в
`AnalysisResult.pipeline_debug` всегда.

Дополнительно — счётчик langdetect-вызовов в parse_pdf_bytes:
```python
langdetect_calls_count: int = 0
detect_lang_llm_used: bool = False
```

Это даст точную картину для последующих шагов.

---

## ШАГ 2 — Убрать LLM detect_language из шаблонного пути

`signfinder/pdf/language.py::detect_language()` сейчас вызывает LLM если langdetect
дал не-supported код. Для шаблонного пути это лишнее: matcher работает по fingerprint,
а не по точному коду языка.

### Решение

Разделить функцию на две:

```python
def detect_language_fast(doc) -> str:
    """Быстрая детекция БЕЗ LLM. Возвращает langdetect-код или 'unknown'."""
    parser_lang = (getattr(doc, "language", "") or "").lower()[:2]
    if parser_lang in SUPPORTED:
        return parser_lang
    # Не в supported (mk-каша определилась как bg/hr) — возвращаем как есть
    return parser_lang if parser_lang else "unknown"


def detect_language(doc, llm: Optional[LLMClient] = None) -> str:
    """Полная детекция С LLM fallback. Только для пайплайна."""
    # ... существующий код без изменений
```

### Обновить analyze() — вызывать fast-версию ДО matcher

```python
def analyze(...) -> AnalysisResult:
    doc = parse_pdf_bytes(pdf_bytes, filename=filename)

    # БЫСТРАЯ детекция — для matcher достаточно
    lang_fast = language or detect_language_fast(doc)
    if not lang_fast or lang_fast == "unknown":
        lang_fast = "ru"

    # fingerprint + matcher работают на lang_fast
    fp = compute_fingerprint(fitz_doc, lang_fast)
    matcher = find_matching_templates(fitz_doc, lang_fast, ...)

    # Шаблонный путь — выходим БЕЗ LLM-вызова detect_language
    if matcher.traffic_light == "green" and matcher.best_match:
        ...
        return AnalysisResult(traffic_light="green", ...)

    # Только в полном пайплайне — точная детекция с LLM fallback
    lang = detect_language(doc, llm=self.llm) if lang_fast not in SUPPORTED else lang_fast

    pipeline = run_pipeline_auto_1(doc=doc, language=lang, ...)
```

**Ожидаемый эффект:** шаблонный путь -2-3 с.

---

## ШАГ 3 — Кэш langdetect в parse_pdf_bytes

Сейчас `langdetect.detect()` зовётся 2N+1 раз для dual-column документа из N страниц.
Достаточно 1-2 вызова на документ:

### Решение

В `parse_pdf_bytes()`:
1. Определить язык документа ОДИН РАЗ по полному тексту (как раньше).
2. Для dual-column страниц — определить языки колонок ТОЛЬКО на ПЕРВОЙ dual-странице,
   запомнить mapping (язык_левой, язык_правой), применить ко всем остальным dual-страницам.

```python
cached_left_lang: str | None = None
cached_right_lang: str | None = None

for page_num, page in enumerate(doc):
    words_raw = page.get_text("words")
    pw = page.rect.width
    gutter = _detect_gutter(words_raw, pw)

    if gutter:
        left_text = _build_column_text(words_raw, x_max=gutter)
        right_text = _build_column_text(words_raw, x_min=gutter)
        page_text = left_text + "\n---\n" + right_text

        # Детектим язык колонок ТОЛЬКО ОДНАЖДЫ
        if cached_left_lang is None:
            try:
                cached_left_lang = _detect(left_text[:500]) if left_text.strip() else "unknown"
            except Exception:
                cached_left_lang = "unknown"
            try:
                cached_right_lang = _detect(right_text[:500]) if right_text.strip() else "unknown"
            except Exception:
                cached_right_lang = "unknown"

        page_langs = list(dict.fromkeys([cached_left_lang, cached_right_lang]))
        p_layout = "dual_column_vertical"
    else:
        page_text = page.get_text()
        page_langs = []
        p_layout = "single_column"
        gutter = None
    ...
```

**Ожидаемый эффект:** parse_pdf_bytes для 6-стр dual-документа: ~1500 мс → ~400 мс.

---

## ШАГ 4 — Кэш markers/profile per-analyze

`load_markers()` и `load_signer_profile_by_id()` читают JSON-файлы с диска при каждом
вызове `get_markers_for_language()`, `get_aliases_for_language()`. За один пайплайн
это 3-5 чтений одного файла.

### Решение

Добавить простой кэш на уровень модуля settings.py с инвалидацией по mtime
(или TTL 60с — проще).

```python
_markers_cache: tuple[float, dict] | None = None
_profiles_cache: dict[str, tuple[float, dict]] = {}

def load_markers(storage):
    global _markers_cache
    now = time.time()
    if _markers_cache and now - _markers_cache[0] < 60:
        return _markers_cache[1]
    # ... существующий код чтения
    _markers_cache = (now, result)
    return result
```

Аналогично для `load_signer_profile_by_id`.

ВАЖНО: кэш TTL короткий (60с), не вечный. Чтобы изменения через UI применялись
к следующему analyze() без перезапуска.

**Ожидаемый эффект:** -100-200 мс на пайплайн.

---

## ШАГ 5 — Ограничить step4 паттерны

Сейчас для dual-column LLM генерирует 31-46 паттернов из мёрженных маркеров двух
языков. Большинство — дублирующие комбинации.

### Решение

В промпте step4 (`signfinder/prompts/regex_generation.py` или где он живёт) добавить
явное ограничение:

```
ВАЖНО: верни НЕ БОЛЕЕ 15 наиболее вероятных паттернов. Не плоди декартовы
произведения marker_words × underline_patterns — сгенерируй только те которые
реалистично встретятся в этом конкретном документе.
```

Плюс детерминированный пост-фильтр после LLM — убрать паттерны которые
семантически дублируются (одинаковая структура, разные слова из одного списка).

**Ожидаемый эффект:** step4 LLM с 3 с до 1.5 с.

---

## Bump + деплой

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.19.0: performance optimizations (timings, fast lang detect, caches)"
git push origin main

cd C:\work\SignPDFMVPLocal
docker compose build --no-cache api
docker compose up -d --force-recreate api
docker compose logs api 2>&1 | Select-String "Core v"
```

Bump: core `__init__.py` + `pyproject.toml` → 1.19.0, CLAUDE.md.

---

## Контроль регрессии

ОБЯЗАТЕЛЬНО прогнать весь корпус ДО и ПОСЛЕ:
- Русские договора (5+): шаблон применяется как раньше, anchors на месте
- PL/MK 6 документов: dual-column работает, профиль borisov определяется
- Замеры в `pipeline_debug.timings_ms`:
  - parse_pdf_bytes < 500 мс для 6 стр
  - detect_lang_llm_used == false для шаблонного пути
  - total_ms < 1500 мс для шаблонного пути
  - total_ms < 10000 мс для полного пайплайна

Если регрессия по функционалу — откат, разбираемся пошагово.

---

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
Сначала Шаг 1 (тайминги) — измеряем что есть. Потом Шаги 2-5 по одному с замерами
после каждого. Не делать всё разом — потеряем причинно-следственную связь.
