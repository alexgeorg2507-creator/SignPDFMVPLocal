# SignFinder v1.18.7b — Маркеры всех языков + многострочные паттерны подписи

Прочитай `C:\work\CLAUDE.md` перед началом.
Изменения только в signfinder-core: settings.py + auto1.py.
Деплой: --no-cache rebuild api.

Содержит ДВА фикса для двуязычных документов — без каждого из них они не работают.

---

## ФИКС 1 — Объединённые маркеры для всех языков документа

### Проблема
Pipeline определяет language="mk" и берёт маркеры только для "mk".
Английские маркеры ("Signature", "President") не попадают в промпт.

### Файл: `signfinder-core/signfinder/pipeline/settings.py`

Добавить функцию рядом с `get_markers_for_language`:

```python
def get_markers_for_languages(
    storage: Optional[StorageBackend],
    languages: list[str],
) -> dict:
    """Объединённый блок маркеров для списка языков (dual-column).

    Списки объединяются без дублей. Скалярные значения — из первого языка.
    Пример: ["mk", "en"] → marker_words включает и "Потпис" и "Signature".
    """
    if not languages:
        return {}
    result: dict = {}
    for lang in languages:
        block = get_markers_for_language(storage, lang)
        for key, val in block.items():
            if isinstance(val, list):
                existing = result.setdefault(key, [])
                for item in val:
                    if item not in existing:
                        existing.append(item)
            else:
                result.setdefault(key, val)
    return result
```

### Файл: `signfinder-core/signfinder/pipeline/auto1.py`

Добавить `get_markers_for_languages` в импорт из settings.

В `run_pipeline_auto_1`, после `debug: dict = {}` — определить effective_language и markers:

```python
    doc_languages = getattr(doc, "languages", []) or [language]
    if len(doc_languages) > 1:
        effective_language = ", ".join(doc_languages)
        effective_markers = get_markers_for_languages(storage, doc_languages)
    else:
        effective_language = language
        effective_markers = get_markers_for_language(storage, language)

    debug["effective_language"] = effective_language
    debug["doc_languages"] = doc_languages
```

Передать `effective_language` в step3:
```python
    our_side, err = run_step3(doc, effective_language, storage, llm, debug, signer_id=signer_id)
```

Передать markers_override в step4 (добавить параметр markers_override в run_step4):
```python
def run_step4(
    doc, lang, our_side, storage, llm, debug,
    markers_override: dict | None = None,
) -> tuple:
    markers_block = markers_override if markers_override is not None \
        else get_markers_for_language(storage, lang)
    ...
```

Вызов из run_pipeline_auto_1:
```python
    patterns, err = run_step4(
        doc, effective_language, our_side, storage, llm, debug,
        markers_override=effective_markers,
    )
```

Заменить `get_markers_for_language(storage, language)` в теле функции на
`effective_markers` (структурные паттерны, signer_underscore_patterns — без изменений,
они работают через алиасы, не маркеры).

---

## ФИКС 2 — Многострочные паттерны подписи (КОРНЕВАЯ ПРИЧИНА)

### Проблема
**ПРОВЕРЕНО на корпусе клиента:** все 31 паттерн сгенерированы и 0 мест найдено.

Причина: в PL/MK документах подпись-блок — **три строки вертикально**:
```
УПРАВИТЕЛ                          ← роль
_____________________              ← подчёркивание
Вадим Борисов                      ← имя
```

А все паттерны требуют текст+подчёркивание **на одной строке** (`[^\n]`):
```
_{3,}[^\n]{0,20}Вадим              ← НЕ матчится (\n между ___ и Вадим)
УПРАВИТЕЛ[^\n]{0,50}_{3,}         ← НЕ матчится (\n между УПРАВИТЕЛ и ___)
```

В русских договорах: `_________ Лебедев А.П.` — одна строка.

Плюс функция `_normalize_sameline` специально убивает кросс-строчные паттерны
(`[\s\S]` → `[^\n]`). Это правильно для русских, но убивает PL/MK.

**Тест на реальном тексте (Agreement последняя стр, колонки разделены):**
```
_{3,}[^\n]{0,20}Вадим   → 0 матчей
_{3,}\n[^\n]{0,20}Вадим  → 1 матч  ← ЭТО РАБОТАЕТ
```

### Решение: добавить многострочные паттерны для фамилии подписанта

В `_signer_underscore_patterns` (auto1.py) добавить ВТОРОЙ набор паттернов
с `\n\s*` между подчёркиванием и именем:

```python
def _signer_underscore_patterns(
    storage: StorageBackend, language: str, our_side: dict, signer_id: str = "default",
) -> list[str]:
    patterns: list[str] = []
    for surname in _extract_surnames(storage, language, our_side, signer_id=signer_id):
        esc = re.escape(surname)
        # Однострочный (русский формат): ____ Лебедев
        patterns.append(rf"_{{3,}}[^\n]{{0,20}}{esc}")
        # Многострочный (PL/MK формат): ____\nВадим Борисов
        patterns.append(rf"_{{3,}}\n[^\n]{{0,20}}{esc}")
    return patterns
```

### Не нормализовать многострочные паттерны

В `_normalize_sameline` убедиться что она НЕ трогает НАШИ многострочные
паттерны (они используют `\n` явно, не `[\s\S]`). Текущая реализация заменяет
только `[\s\S]` → `[^\n]` — это ок, наши `\n` паттерны она не задевает.
Проверить и не менять.

### Дополнительно: многострочные структурные паттерны

В финальном пуле паттернов (после LLM + signer + structural) добавить
многострочные варианты для ключевых маркер-слов. Это делается НЕ в промпте,
а в `run_pipeline_auto_1`, после сборки `final_patterns`:

```python
    # Многострочные паттерны для документов с вертикальной компоновкой подписи
    # (роль\n___\nимя вместо роль _____ имя)
    if getattr(doc, "layout", "single_column") == "dual_column_vertical":
        multiline_extra = []
        # marker_word → \n → ___
        for mw in effective_markers.get("marker_words", []):
            esc_mw = re.escape(mw)
            p = rf"{esc_mw}[^\n]{{0,10}}\n[^\n]{{0,10}}_{{3,}}"
            try:
                re.compile(p, re.IGNORECASE | re.UNICODE)
                if p not in final_patterns:
                    multiline_extra.append(p)
            except re.error:
                pass
        final_patterns.extend(multiline_extra)
        debug["multiline_extra_patterns"] = multiline_extra
```

---

## Bump + деплой

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.18.8: merged multilang markers + multiline signature patterns"
git push origin main

cd C:\work\SignPDFMVPLocal
docker compose build --no-cache api
docker compose up -d --force-recreate api
docker compose logs api 2>&1 | Select-String "Core v"
```

Bump → 1.18.8, CLAUDE.md.

---

## Тест

### Agreement (mk+en) — КЛЮЧЕВОЙ:
1. `effective_language` = "mk, en" (не просто "mk")
2. `final_patterns` содержит и `_{3,}\n[^\n]{0,20}Борисов` и `_{3,}\n[^\n]{0,20}Borisov`
3. `anchors ≥ 2` на последней странице (по одному на каждую колонку)
4. Подпись в обеих колонках в подписанном PDF

### Регрессия (русский договор):
- `effective_language` = "ru" (один язык)
- `_normalize_sameline` не трогает наши `\n`-паттерны
- Однострочные паттерны `_{3,}[^\n]{0,20}Лебедев` продолжают работать
- Результат без изменений

### Debug JSON — что проверить:
```
effective_language: "mk, en"
doc_languages: ["mk", "en"]
signer_underscore_patterns: [
  "_{3,}[^\n]{0,20}Вадим",
  "_{3,}\n[^\n]{0,20}Вадим",      ← НОВЫЙ
  "_{3,}[^\n]{0,20}Борисов",
  "_{3,}\n[^\n]{0,20}Борисов"     ← НОВЫЙ
]
multiline_extra_patterns: [...] (если dual_column)
step5_matches_count: > 0
```

---

## Что НЕ делается здесь

- Overlay sign_above_line уже в v1.18.7 (если включён в настройках)
- Macedonian langdetect (определяется как bg/mk — нас устраивает)
- Dedup x-bucket уже в v1.18.7

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
