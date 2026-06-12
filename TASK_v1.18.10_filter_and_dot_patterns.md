# SignFinder v1.18.10 — Два фикса: направленный фильтр + обратные паттерны точек

Прочитай `C:\work\CLAUDE.md` перед началом.
Изменения только в signfinder-core: pipeline/auto1.py.
Деплой: --no-cache rebuild api.

---

## ДИАГНОСТИКА (из debug JSON)

### БАГ 1 — Agreement: ложный якорь ДОО Скопје всё ещё проходит фильтр

our_side_filter показывает: before=3, after=3 → фильтр НИЧЕГО не убрал.
Причина: окно ±200 символов двунаправленное. "Innowise" находится ~40 символов
ПОСЛЕ клиентского якоря в тексте колонки (следующий блок в левой колонке) →
попадает в окно → ложный якорь сохраняется.

Структура текста левой колонки:
  ОВЛАСТЕНО ЛИЦЕ
  _____________________   ← anchor[0] (КЛИЕНТ, x=60, y=178)
  Innowise Sp. z o.o...  ← ~40 символов ниже → попадает в текущее окно ±200

Нужно: смотреть ТОЛЬКО перед якорем, не после. Окно: 80 символов назад.

### БАГ 2 — IndividualProject: точки вместо подчёркиваний, обратный порядок

Реальный текст страницы 3 (из debug):
  .................................................. ..........................................................
  Innowise Sp. z o.o (d/b/a Innowise Group)
  ( ) (Agent)

Порядок: сначала точки, потом название компании (НЕ наоборот).
LLM генерирует: Innowise[...]{...}\.{5,} (Innowise → точки) → 0 матчей.
Нужно: \.{5,}\n[^\n]{0,10}Innowise (точки → Innowise) → 1 матч.

---

## ФАЙЛ — `signfinder-core/signfinder/pipeline/auto1.py`

### Правка 1: `_filter_by_our_side_context` — только вперёд, 80 символов

Заменить логику поиска контекста:

Было:
```python
ctx_start = max(0, match_pos - window_chars)
ctx_end = min(len(page_text), match_pos + len(anchor_text) + window_chars)
ctx = page_text[ctx_start:ctx_end]
```

Стало (смотрим ТОЛЬКО перед якорем, 80 символов):
```python
ctx_start = max(0, match_pos - 80)
ctx_end = match_pos  # ← только то что ПЕРЕД якорем
ctx = page_text[ctx_start:ctx_end]
```

Результат:
- Якорь ДОО Скопје: 80 символов перед ним — только "ОВЛАСТЕНО ЛИЦЕ" → нет Innowise → ФИЛЬТРУЕТСЯ ✓
- Якорь Innowise/УПРАВИТЕЛ: 80 символов перед ним — "Innowise Group:" → есть → ОСТАЁТСЯ ✓
- Якорь Innowise/President: 80 символов перед ним — "Innowise Group:" → есть → ОСТАЁТСЯ ✓

Убрать параметр `window_chars` из сигнатуры (он больше не используется).

### Правка 2: обратные паттерны для точечных линий (marker → компания)

Сейчас в `run_pipeline_auto_1`, после сборки `final_patterns`, уже генерируются
`multiline_extra` только для `dual_column_vertical`. Нужно добавить обратные паттерны
для ТОЧЕЧНЫХ линий (`.{5,}`) для ВСЕХ документов (не только dual_column).

Добавить функцию:
```python
def _add_reverse_dot_patterns(
    final_patterns: list[str],
    our_side: dict | None,
    signer_id: str = "default",
    storage = None,
) -> list[str]:
    """Добавить паттерны \.{5,}\nX для случаев когда точечная линия ПЕРЕД названием.

    IndividualProject формат:
      ......................................................
      Innowise Sp. z o.o (d/b/a Innowise Group)
      (Agent)
    Нужен паттерн: \.{5,}\n[^\n]{0,10}Innowise
    """
    if not our_side:
        return final_patterns

    extras = []
    # Собрать короткие ядра компании и подписанта
    anchors_to_check = []
    le = (our_side.get("legal_entity") or "").strip()
    if le:
        # Первые 15 символов как ядро
        anchors_to_check.append(le[:15])
    for role in (our_side.get("roles") or []):
        r = (role or "").strip()
        if r and len(r) > 3:
            anchors_to_check.append(r)

    for anchor in anchors_to_check:
        try:
            esc = re.escape(anchor)
            # Точки → перевод строки → компания/роль
            p_dot_nl = rf"\.{{5,}}\n[^\n]{{0,15}}{esc}"
            # Точки на той же строке что и компания (редко, но бывает)
            p_dot_same = rf"\.{{5,}}[^\n]{{0,30}}{esc}"
            for p in [p_dot_nl, p_dot_same]:
                re.compile(p, re.IGNORECASE | re.UNICODE)
                if p not in final_patterns:
                    extras.append(p)
        except re.error:
            pass

    return final_patterns + extras
```

Вызов в `run_pipeline_auto_1`, после сборки `final_patterns` и перед step5:
```python
    # Обратные паттерны для точечных линий (\.{5,} → название компании)
    # Работает для всех документов, не только dual_column
    final_patterns = _add_reverse_dot_patterns(final_patterns, our_side)
    debug["final_patterns"] = final_patterns  # обновить в debug
```

---

## Bump + деплой

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.18.10: directional our_side filter + reverse dot patterns"
git push origin main

cd C:\work\SignPDFMVPLocal
docker compose build --no-cache api
docker compose up -d --force-recreate api
docker compose logs api 2>&1 | Select-String "Core v"
```

Bump → 1.18.10, CLAUDE.md.

---

## Ожидаемые результаты

### Agreement (mk+en):
- anchors = 2 (не 3): клиентский блок отфильтрован
- Обе подписи у Innowise (левая + правая колонка)
- debug: our_side_filter.anchors_after_filter = 2

### IndividualProject (en, single_col):
- В final_patterns появятся:
  `\.{5,}\n[^\n]{0,15}Innowise`
  `\.{5,}\n[^\n]{0,15}Agent`
- anchors ≥ 1 (точечная линия над Innowise найдена)
- Подпись поставлена над точечной линией

### Регрессия (русский, Лебедев):
- Фильтр: "Инлайн технолоджис" в 80 символах перед якорем → проходит ✓
- Обратные паттерны: точек нет → final_patterns не меняются ✓

---

## Что НЕ делается здесь

- Двухколоночный гутер для страницы подписи IndividualProject
  (детектор говорит single_column — и это приемлемо, важно что паттерн находит якорь)
- our_side: None в API-ответе (косметически, не мешает работе пайплайна)

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
