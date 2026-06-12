# SignFinder v1.18.21 — Фикс: our_side фильтр только для dual-column

Прочитай `C:\work\CLAUDE.md` перед началом.
Изменения только в signfinder-core, один файл: pipeline/auto1.py.
Деплой: --no-cache rebuild api.

---

## Диагностика (из debug JSON, русский договор v1.18.20)

step5_matches = 6 (паттерны отработали корректно)
anchors = 1     (фильтр убил 5 правильных якорей, оставил 1 неправильный)

Выживший якорь: text='. Минска 13.11.2014 г. __________', pattern=''
  → это строка с датой, не место подписи
  → pattern='' → _find_underscore_anchor → case 5 fallback → неверная позиция
  → на PDF получается четырёхугольник вместо подписи

Отфильтрованы (5 правильных):
  Заказчик[^\n]{0,50}_{3,}
  _{3,}[^\n]{0,20}Лебедев
  и ещё 3

Почему фильтр убил правильные якоря:
  _filter_by_our_side_context смотрит ctx = page_text[match_pos - 80 : match_pos]
  Для паттерна Заказчик_____:
    - match_pos = позиция "Заказчик" в тексте
    - ctx = [match_pos-80 : match_pos] = текст ДО "Заказчик"
    - синоним "заказчик" находится В "Заказчик", то есть НА match_pos, а не ДО
    - в окно не попадает → фильтруется как чужой блок ❌

Для даты-якоря (выжил):
  - Рядом по тексту случайно оказался текст нашей стороны (реквизиты) → прошёл

---

## Корневая причина

_filter_by_our_side_context был написан для ОДНОЙ задачи: в dual-column документах
(Innowise Agreement) отделить блок клиента (ДОО Скопје) от нашего блока (Innowise).
Для single_column документов фильтр НЕ нужен — step3 уже корректно определил нашу
сторону, LLM-паттерны (Заказчик, Лебедев) уже нашей стороны.

---

## Фикс — один файл, одна строка

`signfinder-core/signfinder/pipeline/auto1.py`

В `run_pipeline_auto_1`, найти блок вызова фильтра:

```python
    if our_side:
        matches = _filter_by_our_side_context(
            matches, [p.text for p in doc.pages], our_side
        )
        debug["our_side_filter"] = {"anchors_after_filter": len(matches)}
```

Заменить на:

```python
    # Фильтр по нашей стороне — ТОЛЬКО для dual_column_vertical.
    # Цель: убрать ложные блоки КЛИЕНТА когда на одной странице два похожих блока.
    # Для single_column не нужен: step3 уже нашёл нашу сторону, паттерны корректны.
    if our_side and getattr(doc, "layout", "single_column") == "dual_column_vertical":
        matches = _filter_by_our_side_context(
            matches, [p.text for p in doc.pages], our_side
        )
        debug["our_side_filter"] = {
            "applied": True,
            "anchors_after_filter": len(matches),
        }
    else:
        debug["our_side_filter"] = {
            "applied": False,
            "reason": "single_column — filter skipped",
        }
```

---

## Bump + деплой

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.18.21: our_side context filter only for dual_column_vertical"
git push origin main

cd C:\work\SignPDFMVPLocal
docker compose build --no-cache api
docker compose up -d --force-recreate api
docker compose logs api 2>&1 | Select-String "Core v"
```

Bump → 1.18.21, CLAUDE.md.

---

## Тест

### Регрессия (русский, Лебедев):
- our_side_filter.applied = false (single_column → фильтр не применяется)
- anchors = все что нашёл step5 (Заказчик_____, Лебедев, etc.)
- Подпись ставится корректно, не четырёхугольник

### Innowise (Agreement mk+en, dual_column):
- our_side_filter.applied = true
- Клиентский блок (ДОО Скопје) отфильтрован
- Якоря только у блоков Innowise

### debug JSON — что проверить:
```
our_side_filter.applied: false  ← для русского
our_side_filter.applied: true   ← для двуязычного
anchors: ≥ 2 для русского договора (раньше было 1)
```

---

## Доп: проверить паттерн='' (пустой pattern)

Якорь который выжил имеет pattern=''. Разобраться как он попал:
- anchor с пустым pattern не имеет смысловой позиции → _find_underscore_anchor
  падает в case 5 → неверная позиция
- Вероятнее всего это anchor из шаблона без pattern (template-based anchor)
  или тестовый anchor без заполненного поля

Если после фикса выше пустой-pattern якорь всё равно попадает в anchors — найти
где он создаётся и добавить guard:

```python
# В run_pipeline_auto_1 после сборки matches:
matches = [m for m in matches if getattr(m, "pattern", None) or
           (isinstance(m, dict) and m.get("pattern"))]
```

Но сначала проверить — после фикса фильтра он должен исчезнуть из-за того что
правильные якоря не отфильтровываются и побеждают в dedup.

---

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
