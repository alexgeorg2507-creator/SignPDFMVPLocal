# SignFinder v1.18.7 — Подписи в обеих колонках + подпись над линией

Прочитай `C:\work\CLAUDE.md` перед началом.

Затрагиваемые репозитории (локальная версия в Docker):
- signfinder-core: parser.py, dedup.py, overlay.py, signfinder/__init__.py
- signfinder-api: app/models/settings.py
- SignPDFMVPLocal/streamlit/views/4_Nastroyki.py (минимальная правка)

Деплой после: --no-cache rebuild api + rebuild streamlit.

---

## Контекст и архитектура решения (Путь А)

Двуязычные документы (польско-английские, македонско-английские) имеют вертикальное
деление: левая колонка (один язык) + правая (другой). Сейчас PyMuPDF читает текст как
каша. Нужно: читать колонки раздельно, склеивать левая→правая, слова оставлять с
реальными bbox. Подпись надо поставить в ОБЕ колонки.

**Путь А (выбранный):** одна страница, текст = левая_колонка + "\n---\n" + правая_колонка.
Слова с реальными bbox остаются в page.words. Pattern matching работает по обоим языкам.
Деление — через обнаружение вертикального коридора (35-65% ширины страницы).

**Алгоритм детектора коридора (проверен на корпусе клиента, 6 документов):**
```python
def _detect_gutter(words, page_width):
    lo, hi = int(page_width * 0.35), int(page_width * 0.65)
    best_cut, best_cross = None, len(words) + 1
    for cut in range(lo, hi, 5):
        crossing = sum(1 for w in words if w[0] < cut < w[2])  # w[0]=x0, w[2]=x1
        if crossing < best_cross:
            best_cross, best_cut = crossing, cut
    return best_cut if best_cross <= 2 else None
```
Результаты на корпусе:
- Agreement (mk+en):      коридор x=293, пересечений=0 → ДВЕ КОЛОНКИ
- Amendment (en+pl):      коридор x=314, пересечений=0 → ДВЕ КОЛОНКИ
- Enclosure2 (en+pl):     коридор x=293, пересечений=0 → ДВЕ КОЛОНКИ
- TechAddendum (en+pl):   коридор x=283, пересечений=1 → ДВЕ КОЛОНКИ
- IndividualProject (en):  коридор x=363, пересечений=10 → одна колонка ✅

---

## Файл 1 — `signfinder-core/signfinder/pdf/parser.py`

### 1.1 Расширить модели данных

```python
@dataclass
class ParsedPage:
    page_num: int
    text: str
    words: list = field(default_factory=list)
    layout: str = "single_column"          # "single_column" | "dual_column_vertical"
    gutter_x: float | None = None          # x-координата коридора (pt)
    languages: list = field(default_factory=list)  # ["en"] или ["mk", "en"]


@dataclass
class ParsedDocument:
    filename: str
    language: str                          # первичный язык (обратная совместимость)
    languages: list = field(default_factory=list)  # все языки документа
    layout: str = "single_column"
    gutter_x: float | None = None
    pages: list = field(default_factory=list)
    pdf_bytes: bytes = b""
```

### 1.2 Добавить функцию `_detect_gutter`

```python
def _detect_gutter(words_raw: list, page_width: float) -> float | None:
    """Обнаружить вертикальный коридор между колонками.

    words_raw — список кортежей из fitz get_text("words"): (x0,y0,x1,y1,text,...)
    Ищет полосу x в центральной зоне (35-65% ширины), через которую проходит ≤2 слова.
    Возвращает x-координату коридора или None если одна колонка.

    ПРОВЕРЕНО на 6 документах клиента: безошибочно делит 4 двуязычных (0-1 пересечение)
    от 1 одноколоночного (10 пересечений).
    """
    if not words_raw:
        return None
    lo, hi = int(page_width * 0.35), int(page_width * 0.65)
    best_cut, best_cross = None, len(words_raw) + 1
    for cut in range(lo, hi, 5):
        crossing = sum(1 for w in words_raw if w[0] < cut < w[2])
        if crossing < best_cross:
            best_cross, best_cut = crossing, cut
    return float(best_cut) if (best_cross <= 2 and best_cut is not None) else None
```

### 1.3 Обновить `parse_pdf_bytes`

Для каждой страницы:
1. Взять `words_raw = page.get_text("words")`
2. Вызвать `_detect_gutter(words_raw, page.rect.width)`
3. Если гутер найден: разделить слова на левую/правую колонки, построить текст раздельно
4. Текст страницы = левая_колонка + "\n---\n" + правая_колонка
5. `page.words` = все слова с реальными bbox (не менять! pattern_extractor их использует)
6. Определить язык каждой колонки через `langdetect.detect`
7. `ParsedPage.layout` = "dual_column_vertical", `gutter_x`, `languages` = [lang_left, lang_right]

```python
def _build_column_text(words_raw: list, x_max: float | None = None,
                       x_min: float | None = None) -> str:
    """Собрать текст из слов в горизонтальном диапазоне, сортируя по (top, x0)."""
    if x_max is not None:
        ws = [w for w in words_raw if w[2] <= x_max]  # w[2]=x1 левее коридора
    elif x_min is not None:
        ws = [w for w in words_raw if w[0] >= x_min]  # w[0]=x0 правее коридора
    else:
        ws = words_raw
    ws_sorted = sorted(ws, key=lambda w: (round(w[1]), w[0]))  # по (top, x0)
    # Группируем по строкам (y близкие → одна строка)
    lines, cur_line, cur_y = [], [], None
    for w in ws_sorted:
        wy = round(w[1])
        if cur_y is None or abs(wy - cur_y) > 3:
            if cur_line:
                lines.append(" ".join(c[4] for c in cur_line))
            cur_line, cur_y = [w], wy
        else:
            cur_line.append(w)
    if cur_line:
        lines.append(" ".join(c[4] for c in cur_line))
    return "\n".join(lines)
```

Обновлённый основной цикл `parse_pdf_bytes`:
```python
for page_num, page in enumerate(doc):
    words_raw = page.get_text("words")
    pw = page.rect.width

    gutter = _detect_gutter(words_raw, pw)

    if gutter:
        # Две колонки: текст левая→правая
        left_text = _build_column_text(words_raw, x_max=gutter)
        right_text = _build_column_text(words_raw, x_min=gutter)
        page_text = left_text + "\n---\n" + right_text

        # Язык каждой колонки
        try:
            lang_left = detect(left_text[:500]) if left_text.strip() else "unknown"
        except Exception:
            lang_left = "unknown"
        try:
            lang_right = detect(right_text[:500]) if right_text.strip() else "unknown"
        except Exception:
            lang_right = "unknown"
        page_langs = list(dict.fromkeys([lang_left, lang_right]))  # уникальные, по порядку
        p_layout = "dual_column_vertical"
    else:
        page_text = page.get_text()
        page_langs = []  # заполнится ниже из full_text
        p_layout = "single_column"
        gutter = None

    words = [Word(text=w[4], bbox=(w[0], w[1], w[2], w[3])) for w in words_raw]
    full_text_parts.append(page_text)
    pages.append(ParsedPage(
        page_num=page_num, text=page_text, words=words,
        layout=p_layout, gutter_x=gutter, languages=page_langs,
    ))
```

После цикла — определить язык и layout документа:
```python
# Язык документа (из полного текста, обратная совместимость)
full_text = "\n".join(full_text_parts)[:5000]
try:
    from langdetect import detect
    language = detect(full_text) if full_text.strip() else "unknown"
except Exception:
    language = "unknown"

# Собрать все языки документа из страниц
all_langs = []
for p in pages:
    for lg in p.languages:
        if lg not in all_langs and lg != "unknown":
            all_langs.append(lg)
if not all_langs:
    all_langs = [language]

# Layout документа: dual если хотя бы одна страница dual
doc_layout = "dual_column_vertical" if any(
    p.layout == "dual_column_vertical" for p in pages
) else "single_column"
doc_gutter = next((p.gutter_x for p in pages if p.gutter_x is not None), None)

return ParsedDocument(
    filename=filename,
    language=language,
    languages=all_langs,
    layout=doc_layout,
    gutter_x=doc_gutter,
    pages=pages,
    pdf_bytes=pdf_bytes,
)
```

---

## Файл 2 — `signfinder-core/signfinder/pipeline/dedup.py`

### Проблема Шага 2 для двухколоночных документов

Текущий Шаг 2 группирует по `(page_key, text_key)`. Если в левой и правой колонках
один и тот же текст (напр. "Vadim Borisov" в EN+PL документах), якоря схлопываются.

### Фикс: добавить x-bucket к ключу группировки

```python
# Шаг 2: семантические дубли — одна страница, одинаковый text[:30]
# x_bucket: делим по 100pt — колонки обычно разнесены на 250-350pt
groups: dict = defaultdict(list)
for a in step1:
    text_key = (_attr(a, "anchor_text", "") or "")[:30]
    page_key = str(_attr(a, "page_hint", "0"))
    x_bucket = round(float(_bbox(a)[0]) / 100.0)  # bucket: 0-1=левая, 3-4=правая
    groups[(page_key, text_key, x_bucket)].append(a)
```

Остальная логика Шага 2 — без изменений.

Результат: "Vadim Borisov" в x=50 (bucket=0) и "Vadim Borisov" в x=320 (bucket=3)
→ разные группы → не схлопываются → подпись в обеих колонках.

---

## Файл 3 — `signfinder-core/signfinder/pdf/overlay.py`

### 3.1 Добавить `sign_above_line` в `apply_signature`

```python
def apply_signature(
    pdf_bytes: bytes,
    matches: list,
    png_bytes: bytes | None,
    flatten: bool = False,
    scale: float = 1.0,
    use_signature: bool = True,
    use_marker: bool = False,
    marker_color: str = "pink",
    sign_above_line: bool = False,   # ← НОВЫЙ параметр
) -> bytes:
```

### 3.2 Обновить `_find_underscore_anchor` — возвращать y_top

Сигнатура функции (добавить параметр):
```python
def _find_underscore_anchor(page, bbox, pattern: str, above_line: bool = False):
```

В каждом return: вместо `y1` (низ линии) возвращать `y0` (верх) если `above_line=True`.

**Case 1** (pattern starts with `_`):
```python
y_pos = y0 if above_line else y1
return x0 + SIGNATURE_X_OFFSET_PT, y_pos, line_height
```

**Case 4** (search_for "___"):
```python
y_pos = best.y0 if above_line else best.y1
return best.x0 + SIGNATURE_X_OFFSET_PT, y_pos, max(line_height, best.height)
```

**Case 3** (rawdict char '_'):
```python
cb_y = float(cb['bbox'][1]) if above_line else float(cb['bbox'][3])
return float(cb[0]) + SIGNATURE_X_OFFSET_PT, cb_y, line_height
```

**Case 2** (text prefix) и **Case 5** (fallback):
```python
y_pos = y0 if above_line else y1
return ..., y_pos, line_height
```

### 3.3 Передать above_line в вызов _find_underscore_anchor

В `apply_signature`, в цикле по matches:
```python
anchor_x, anchor_y, _ = _find_underscore_anchor(
    page, m.bbox, m.pattern, above_line=sign_above_line
)
```

sig_rect остаётся без изменений:
```python
sig_rect = fitz.Rect(
    anchor_x,
    anchor_y - sig_h,   # когда above_line=True: это y0_линии - sig_h (подпись над линией)
    anchor_x + sig_w,
    anchor_y,           # когда above_line=True: это y0_линии (низ подписи = верх линии)
)
```

---

## Файл 4 — `signfinder-core/signfinder/__init__.py`

В методе `sign()` (или где вызывается `apply_signature`) — добавить чтение
`sign_above_line` из `sign_mode.json` и передачу в `apply_signature`.

```python
sign_mode = sf.storage.read_json("settings/sign_mode.json") or {}
sign_above_line = sign_mode.get("sign_above_line", False)

return apply_signature(
    ...,
    sign_above_line=sign_above_line,
)
```

---

## Файл 5 — `signfinder-api/app/models/settings.py`

В модели `SignModeSettings` (или аналогичной для sign_mode) добавить:
```python
sign_above_line: bool = False
```

---

## Файл 6 — `SignPDFMVPLocal/streamlit/views/4_Nastroyki.py`

В секции «Режим простановки» добавить toggle после `use_mrk`:

```python
sign_above_line = st.checkbox(
    "✍️ Подпись над линией (для двуязычных договоров)",
    value=current_mode.get("sign_above_line", False),
    key="mode_sign_above_line",
    help="Подпись ставится НАД подчёркиванием. Для одноязычных (Лебедев) — выключить.",
)
```

Добавить в `payload` при сохранении:
```python
"sign_above_line": sign_above_line,
```

---

## Bump + деплой

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.18.7: dual-column detection (Путь А) + sign_above_line mode"
git push origin main

cd C:\work\SignPDFMVPLocal
docker compose build --no-cache api
docker compose build streamlit
docker compose up -d --force-recreate api streamlit
docker compose logs api 2>&1 | Select-String "Core v"
```

Bump: core `__init__.py` + `pyproject.toml` → 1.18.7, CLAUDE.md.

---

## Тест

### Регрессия (русский договор):
- layout = single_column (гутер не найден)
- anchors найдены, подпись поставлена
- sign_above_line=False (по умолчанию) → поведение как раньше

### Новое (Innowise EN+PL или MK+EN):
1. Настройки → Режим простановки → включить «Подпись над линией» → Сохранить
2. Загрузить Amendment или Agreement через «Авто-подписание»
3. Ожидаем:
   - `layout = dual_column_vertical` в debug JSON
   - `languages` = ["en", "pl"] или ["mk", "en"]
   - `anchors >= 2` (по одному на каждую колонку — для "Vadim Borisov" EN + "Вадим Борисов" MK)
   - В подписанном PDF: подпись в обеих колонках, расположена НАД подчёркиванием
4. Посмотреть что якоря НЕ схлопнулись (dedup не убрал один из двух)

### Ключевая проверка dedup:
В debug JSON → `all_anchors.total` должен быть ≥ 2 для последней страницы Agreement.
Если total=1 → dedup схлопнул → что-то не так с x-bucket фиксом.

---

## Что НЕ делается в v1.18.7

- Fingerprint двуязычных (будет более стабильным автоматически т.к. текст упорядочен)
- Маркер места подписи для двуязычных — по текущей логике он пойдёт в обе колонки
  автоматически если anchors в обеих (maркер рисуется на правом поле страницы)
- Македонский в langdetect — он определяется как "bg" (болгарский) или "uk", это нормально
  для MVP; важно что ТЕКСТ читается правильно, а не метка языка

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
