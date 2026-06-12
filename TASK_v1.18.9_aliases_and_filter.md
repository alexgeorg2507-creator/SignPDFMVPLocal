# SignFinder v1.18.9 — Два фикса для двуязычных: алиасы + фильтр ложных блоков

Прочитай `C:\work\CLAUDE.md` перед началом.
Изменения только в signfinder-core: settings.py + auto1.py.
Деплой: --no-cache rebuild api.

---

## Диагностика (из debug JSON Agreement_redacted_client_only)

Результат после v1.18.8:
- Якорь [0]: x=60, y=178, text='ДОО Скопје: ОВЛАСТЕНО ЛИЦЕ' → КЛИЕНТ (ложная тревога)
- Якорь [1]: x=60, y=260, text='Innowise Group: УПРАВИТЕЛ' → правильно (левая колонка)
- Правая колонка: 0 якорей (Vadim Borisov не найден)

Два корневых бага:

БАГ 1 — Правая колонка не найдена:
  get_aliases_for_language("mk, en") → lang[:2] = "mk" → только кириллические алиасы
  → signer_underscore_patterns содержит только 'Борисов'/'Вадим' (кириллица)
  → латиница 'Vadim Borisov' в правой колонке не матчится → 0 якорей справа

БАГ 2 — Ложная тревога клиентского блока:
  Паттерн 'ОВЛАСТЕНО ЛИЦЕ\n_{3,}' сработал на блоке ДОО Скопје (это клиент).
  LLM добавил 'ОВЛАСТЕНО ЛИЦЕ' как общий македонский маркер, не зная что в
  данном документе это маркер клиента, а не Innowise.

---

## Файл 1 — `signfinder-core/signfinder/pipeline/settings.py`

### Фикс get_aliases_for_language: поддержка составного языка

Текущий код:
```python
lang = (language or "").lower()[:2]
```

Заменить на:
```python
# Составной язык ("mk, en") → набор кодов {"mk", "en"}
raw_langs = (language or "")
langs = {l.strip()[:2].lower() for l in raw_langs.split(",") if l.strip()}
if not langs:
    langs = {"ru"}
```

Обновить фильтрацию алиасов:
```python
def _filter(key: str) -> list[str]:
    all_aliases = profile.get(key, [])
    # Берём алиасы для ВСЕХ запрошенных языков
    by_langs = [
        a["value"] for a in all_aliases
        if a.get("language", "")[:2].lower() in langs
        and a.get("value", "").strip()
    ]
    if by_langs:
        return by_langs
    # Fallback: все алиасы (как раньше)
    return [a["value"] for a in all_aliases if a.get("value", "").strip()]
```

Результат для "mk, en": вернёт И "Вадим Борисов" (mk) И "Vadim Borisov" (en).
Результат для "ru" (одиночный): поведение без изменений (обратная совместимость).

---

## Файл 2 — `signfinder-core/signfinder/pipeline/auto1.py`

### Фикс: пост-фильтр совпадений по our_side синонимам

После сбора matches в step5, перед формированием anchors — добавить фильтрацию:
оставить только матчи где наша сторона (our_side) упоминается рядом с якорем.

Добавить функцию `_filter_by_our_side_context`:

```python
def _filter_by_our_side_context(
    matches: list,
    page_texts: list[str],
    our_side: dict | None,
    window_chars: int = 200,
) -> list:
    """Оставить только матчи где рядом (±200 символов) есть наши синонимы.

    Решает проблему ложных блоков клиента: паттерн 'ОВЛАСТЕНО ЛИЦЕ' срабатывает
    и на клиентском блоке, и на нашем — но наш всегда рядом с 'Innowise'.
    """
    if not our_side or not matches:
        return matches

    # Собрать все синонимы нашей стороны (нечувствительно к регистру)
    synonyms = set()
    le = (our_side.get("legal_entity") or "").strip().lower()
    if le:
        # Берём короткое ядро (первые 10 символов названия)
        synonyms.add(le[:10])
    for role in (our_side.get("roles") or []):
        r = (role or "").strip().lower()
        if r and len(r) > 3:
            synonyms.add(r)
    signer = (our_side.get("signer") or "").strip().lower()
    if signer:
        synonyms.add(signer[:8])  # короткий фрагмент фамилии

    if not synonyms:
        return matches  # нет синонимов — не фильтруем

    result = []
    for m in matches:
        page_idx = getattr(m, "page_hint", None) or getattr(m, "page", None)
        if page_idx is None:
            result.append(m)
            continue
        try:
            page_text = page_texts[int(page_idx)].lower()
        except (IndexError, TypeError):
            result.append(m)
            continue

        # Найти позицию матча в тексте страницы
        anchor_text = (getattr(m, "anchor_text", "") or "").strip().lower()
        match_pos = page_text.find(anchor_text[:20]) if anchor_text else -1

        if match_pos == -1:
            # Не нашли позицию — оставляем (не отфильтровываем неуверенно)
            result.append(m)
            continue

        # Контекст ±window_chars вокруг матча
        ctx_start = max(0, match_pos - window_chars)
        ctx_end = min(len(page_text), match_pos + len(anchor_text) + window_chars)
        ctx = page_text[ctx_start:ctx_end]

        # Проверить есть ли хоть один наш синоним в контексте
        found = any(syn in ctx for syn in synonyms)
        if found:
            result.append(m)
        # else: фильтруем — это блок другой стороны

    return result
```

### Вызов пост-фильтра в run_pipeline_auto_1

После получения matches из step5, ДО передачи в dedup:

```python
    # Пост-фильтр: оставить только матчи рядом с нашей стороной
    if our_side and matches:
        page_texts = [p.text for p in doc.pages]
        before_filter = len(matches)
        matches = _filter_by_our_side_context(matches, page_texts, our_side)
        debug["our_side_context_filter"] = {
            "before": before_filter,
            "after": len(matches),
            "synonyms_used": list(synonyms) if our_side else [],
        }
```

Аргументы: `matches` из step5, `page_texts` из doc.pages, `our_side` из step3.
Поле `synonyms` — локальная переменная внутри `_filter_by_our_side_context`,
в debug вынести нельзя напрямую; можно добавить параметр `debug_synonyms: list = None`
или просто пропустить этот факт в debug.

Упрощённый вариант вызова:
```python
    if our_side:
        matches = _filter_by_our_side_context(
            matches, [p.text for p in doc.pages], our_side
        )
        debug["our_side_filter"] = {"anchors_after_filter": len(matches)}
```

---

## Bump + деплой

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.18.9: fix aliases for multi-lang + our_side context filter"
git push origin main

cd C:\work\SignPDFMVPLocal
docker compose build --no-cache api
docker compose up -d --force-recreate api
docker compose logs api 2>&1 | Select-String "Core v"
```

Bump → 1.18.9, CLAUDE.md.

---

## Ожидаемый результат на Agreement (mk+en)

После фикса:
1. signer_underscore_patterns содержит И кириллицу И латиницу:
   ['_{3,}[^\n]{0,20}Вадим', '_{3,}\n[^\n]{0,20}Вадим',
    '_{3,}[^\n]{0,20}Борисов', '_{3,}\n[^\n]{0,20}Борисов',
    '_{3,}[^\n]{0,20}Vadim', '_{3,}\n[^\n]{0,20}Vadim',
    '_{3,}[^\n]{0,20}Borisov', '_{3,}\n[^\n]{0,20}Borisov']

2. anchors = 2, ОБА у Innowise:
   - Левая колонка x≈60, y≈260 (УПРАВИТЕЛ / Вадим Борисов)
   - Правая колонка x≈303, y≈262 (President / Vadim Borisov)

3. Клиентский блок (ДОО Скопје / CEO) — отфильтрован

4. Подписанный PDF: 2 подписи Borisov, обе над линией

### Debug JSON — что проверить:
```
our_side_filter.anchors_after_filter: 2  (было 2 до фикса, должно остаться 2 но правильные)
anchors[0].text: содержит 'Innowise' или 'Борисов' или 'УПРАВИТЕЛ'
anchors[1].text: содержит 'Innowise' или 'Borisov'
```

---

## Регрессия (русский договор)

- get_aliases_for_language("ru") → langs={"ru"} → работает как раньше ✅
- Пост-фильтр: наш синоним 'Инлайн технолоджис' или 'Лебедев' есть в контексте → не фильтрует ✅

---

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
