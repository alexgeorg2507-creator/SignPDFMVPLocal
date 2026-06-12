# SignFinder v1.18.23 — Кластеризация блока подписи + приоритет синонимов + авто над/под

Прочитай `C:\work\CLAUDE.md` перед началом.
Изменения в signfinder-core: anchors/finder.py, pdf/overlay.py, pipeline/auto1.py.
Деплой: --no-cache rebuild api.

ВАЖНО: большая часть инфраструктуры УЖЕ есть. Это точечные правки, не переписывание.
Что уже работает (НЕ трогать):
- _find_signature_bbox клипует линию по колонке (dual-column)
- _expand_line_bbox с max_gap (не склеивает колонки)
- _bbox_contains_signature_line детектит DocuSign \tN\ теги в тексте
- _find_underscore_anchor: case 1 (паттерн с _ или \.) → x0; case 2 (текст-префикс)

---

## Диагностика (что осталось сломанным)

Из debug individual_project (8 якорей, все pattern=''):
1. ВСЕ anchors имеют pattern='' → теряется при маппинге match→anchor → overlay
   падает в fallback case 5, dedup группирует слепо
2. На одном блоке подписи 5 якорей (legal_entity + role + signer нашли свои строки)
   → подпись у случайного (победил (Agent))
3. DocuSign тег \e1\ — не используется как точка подписи напрямую

---

## ФИКС 1 — pattern не теряется (технический, КОРНЕВОЙ)

### Проблема
В `regex_match_to_anchor` (finder.py) pattern передаётся в `build_anchor_from_regex_match`,
но в итоговом TextAnchor.generated_pattern оказывается пустым. Проверить
`anchors/builder.py::build_anchor_from_regex_match` — сохраняет ли pattern.

### Действие
Прочитать `signfinder-core/signfinder/anchors/builder.py`, найти
`build_anchor_from_regex_match`. Убедиться что параметр `pattern` пишется в
`generated_pattern` результирующего TextAnchor. Если теряется — починить.

Это первый фикс — без него все остальные бессмысленны (overlay не знает тип привязки).

---

## ФИКС 2 — Кластеризация блока подписи + приоритет синонима

### Принцип (подтверждён оператором)
- Якоря в вертикальном радиусе ~60pt + перекрытие по X = ОДИН блок подписи
- Один блок = ОДНА подпись
- Победитель в блоке — чей синоним РАНЬШЕ в списке профиля (порядок = приоритет)

### Действие
В `pipeline/auto1.py`, после получения matches из step5 и ПЕРЕД формированием
anchors — добавить кластеризацию.

```python
def _cluster_signature_blocks(
    matches: list,
    our_side: dict | None,
    aliases_ordered: list[str],
    y_radius: float = 60.0,
) -> list:
    """Сгруппировать матчи в блоки подписи, выбрать по одному на блок.

    Блок = матчи на одной странице в пределах y_radius по вертикали с X-перекрытием.
    Победитель в блоке — чей контекст содержит синоним, стоящий РАНЬШЕ в
    aliases_ordered (порядок синонимов в профиле = приоритет оператора).
    Если приоритет равный — самый широкий bbox (полная линия, не фрагмент).
    """
    if not matches:
        return matches

    # Приоритет синонима: индекс в aliases_ordered (меньше = важнее)
    def _synonym_rank(m) -> int:
        ctx = (getattr(m, "context", "") or "").lower()
        for i, alias in enumerate(aliases_ordered):
            if alias and alias.lower()[:15] in ctx:
                return i
        return len(aliases_ordered)  # не нашли синоним → низший приоритет

    def _bbox_width(m) -> float:
        b = m.bbox
        return b[2] - b[0]

    # Группировка по странице + вертикальной близости
    clusters: list[list] = []
    for m in sorted(matches, key=lambda x: (x.page, (x.bbox[1] + x.bbox[3]) / 2)):
        m_yc = (m.bbox[1] + m.bbox[3]) / 2
        placed = False
        for cluster in clusters:
            ref = cluster[0]
            if ref.page != m.page:
                continue
            ref_yc = (ref.bbox[1] + ref.bbox[3]) / 2
            # X-перекрытие: матчи одной колонки/блока
            x_overlap = min(m.bbox[2], ref.bbox[2]) > max(m.bbox[0], ref.bbox[0])
            if abs(m_yc - ref_yc) <= y_radius and x_overlap:
                cluster.append(m)
                placed = True
                break
        if not placed:
            clusters.append([m])

    # Выбор победителя в каждом кластере
    winners = []
    for cluster in clusters:
        winner = min(cluster, key=lambda m: (_synonym_rank(m), -_bbox_width(m)))
        winners.append(winner)
    return winners
```

Вызов в run_pipeline_auto_1 (после step5 matches, до anchors):

```python
    # Кластеризация блоков подписи + выбор по приоритету синонима
    if our_side:
        # Собрать синонимы в порядке профиля (company → signer → roles)
        aliases_ordered = []
        le = our_side.get("legal_entity", "")
        if le:
            aliases_ordered.append(le)
        signer = our_side.get("signer", "")
        if signer:
            aliases_ordered.append(signer)
        for r in (our_side.get("roles") or []):
            if r:
                aliases_ordered.append(r)

        before_cluster = len(matches)
        matches = _cluster_signature_blocks(matches, our_side, aliases_ordered)
        debug["clustering"] = {
            "before": before_cluster,
            "after": len(matches),
            "aliases_order": aliases_ordered,
        }
```

ВАЖНО про порядок синонимов: сейчас `our_side` приходит из step3 с полями
legal_entity/signer/roles. Порядок aliases_ordered здесь: компания → подписант → роли.
Это разумный дефолт. Полный «порядок из настроек профиля» — отдельная доработка
(требует чтения profile.json и сопоставления). Сейчас фиксируем company-first.

---

## ФИКС 3 — DocuSign тег как точка подписи

### Принцип (подтверждён на корпусе)
- Наш тег = тег \xN\ геометрически ближайший к нашему синониму
- \e1\ оказался нашим на стр.3 и стр.4 (рядом с Innowise)
- blacklist: \dN\ (дата), \aN\ (инициалы) — не ставить туда подпись

### Действие
В `_find_underscore_anchor` (overlay.py) добавить case 0 (ПЕРЕД case 1):
если в bbox-зоне или рядом есть DocuSign-тег — вернуть его позицию.

```python
    # Case 0: DocuSign-тег рядом с якорем — ставим точно на тег.
    # Тег \tN\ \sN\ \eN\ — текстовое слово с координатами. blacklist \dN\ \aN\.
    try:
        import re as _re
        rawdict = page.get_text("words")  # (x0,y0,x1,y1,text,...)
        ds_tags = [w for w in rawdict
                   if _re.match(r'\\[tse]\d+\\', w[4])]  # только t/s/e, НЕ d/a
        if ds_tags:
            # Ближайший тег к центру нашего якоря (по y, в той же колонке по x)
            best_tag = None
            best_d = float("inf")
            for w in ds_tags:
                tag_yc = (w[1] + w[3]) / 2
                tag_xc = (w[0] + w[2]) / 2
                # В пределах 150pt по y и той же половины страницы
                dy = abs(tag_yc - y_center)
                if dy < best_d and dy < 150:
                    best_d = dy
                    best_tag = w
            if best_tag is not None:
                tag_y = best_tag[1] if above_line else best_tag[3]
                return best_tag[0], tag_y, (best_tag[3] - best_tag[1])
    except Exception:
        pass
```

ВАЖНО: case 0 срабатывает только если теги реально есть. Для русских/обычных
документов rawdict не содержит \xN\ → проваливается в case 1 как раньше.

---

## ФИКС 4 — Авто над/под линией (заменяет глобальный флаг)

### Принцип (подтверждён)
- Ставить туда где есть свободное место (зазор ≥ высота подписи)
- Оба свободны → над (под линией обычно расшифровка ФИО)
- Никуда → ужать подпись

### Действие
Это улучшение, делать ПОСЛЕ фиксов 1-3 если время есть. Заменить параметр
`sign_above_line: bool` на автоопределение в `_find_underscore_anchor`:

```python
def _measure_vertical_gaps(page, x0, y0, y1, sig_w) -> tuple[float, float]:
    """Вернуть (зазор_над, зазор_под) для линии — свободное место по вертикали.

    Зазор = расстояние до ближайшего слова сверху/снизу в той же x-зоне.
    """
    words = page.get_text("words")
    line_yc = (y0 + y1) / 2
    x_lo, x_hi = x0, x0 + sig_w
    gap_above = y0  # от верха страницы
    gap_below = page.rect.height - y1
    for w in words:
        wx0, wy0, wx1, wy1, *_ = w
        # слово пересекает x-зону подписи
        if wx1 < x_lo or wx0 > x_hi:
            continue
        w_yc = (wy0 + wy1) / 2
        if w_yc < line_yc:  # выше линии
            gap_above = min(gap_above, y0 - wy1)
        elif w_yc > line_yc:  # ниже линии
            gap_below = min(gap_below, wy0 - y1)
    return max(0, gap_above), max(0, gap_below)
```

И в apply_signature: вместо `sign_above_line` параметра — вычислять для каждого
match направление автоматически (above если gap_above >= sig_h, иначе below).

ОСТОРОЖНО: это меняет сигнатуру apply_signature. Сохранить обратную совместимость —
оставить sign_above_line как опциональный override (None = авто, True/False = форс).

```python
def apply_signature(..., sign_above_line: bool | None = None):
    # None → авто-определение; True/False → форс (старое поведение)
```

Если авто-режим рискован для регрессии русских — ФИКС 4 отложить, оставить флаг.
Приоритет фиксов: 1 (pattern) > 2 (кластеризация) > 3 (DocuSign) > 4 (авто над/под).

---

## Bump + деплой

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.18.23: signature block clustering + synonym priority + DocuSign tag anchor"
git push origin main

cd C:\work\SignPDFMVPLocal
docker compose build --no-cache api
docker compose up -d --force-recreate api
docker compose logs api 2>&1 | Select-String "Core v"
```

Bump → 1.18.23, CLAUDE.md.

---

## Тест

### IndividualProject (en):
1. anchors имеют непустой pattern (ФИКС 1)
2. На блок подписи — ОДИН якорь, не 5 (ФИКС 2: clustering.after < clustering.before)
3. Подпись у Innowise-блока, не у (Agent)
4. DocuSign-страницы: подпись на месте тега \e1\ (ФИКС 3)

### Agreement (mk+en):
- 2 подписи (левая+правая колонка), по одной на блок
- Не схлопнулись (разные кластеры по x)

### Русский (регрессия):
- Один якорь на блок Заказчик/Подрядчик
- pattern не пустой
- Подпись на месте

### debug:
```
clustering.before > clustering.after  (блоки схлопнулись в победителей)
clustering.aliases_order: [компания, подписант, роли...]
anchors[].pattern: НЕ пустой
```

---

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
Делать по приоритету: ФИКС 1 → проверить pattern непустой → ФИКС 2 → ФИКС 3 → ФИКС 4.
После каждого — прогон корпуса, не копить изменения.
