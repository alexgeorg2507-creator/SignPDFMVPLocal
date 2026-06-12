# SignFinder v1.18.20 — Обновление юнит-тестов под v1.18.x

Прочитай `C:\work\CLAUDE.md` перед началом.
Изменения только в `signfinder-core/tests/`. Деплой не нужен — это тесты.

ЦЕЛЬ: 88 тестов проходят, добавлены новые под фичи v1.18.x.
Проверка после: `docker compose exec api pytest /app/sf_tests -q`

---

## Анализ существующих падений

### Падение 1: `test_dedup.py::test_step1_different_bbox_kept`

```python
a1 = _a("Lessor", "1", bbox=(50.0, 100.0, 200.0, 115.0))   # x0=50, x_bucket=0
a2 = _a("Lessor", "1", bbox=(50.0, 200.0, 200.0, 215.0))   # x0=50, x_bucket=0
```
Тест ожидает 2 якоря (разные bbox), получает 1.

**Причина:** v1.18.7 добавил x_bucket в Шаг 2 dedup. Якоря с одинаковым `(page, text[:30], x_bucket)` — это **дубль регекса в одной колонке** (паттерн нашёл одно слово дважды на разной высоте). dedup корректно схлопывает. Это новое корректное поведение.

**Фикс теста:** имя теста обманчивое — он называется «step1 different bbox kept», но реально проверяет, что разные bbox НЕ дедупаются в Шаге 1 (exact match). Шаг 2 (семантический) их всё равно может схлопнуть. Решение: сделать `text` разным.

### Падение 2: `test_overlay.py::test_signature_x_offset_pt_constant`

```python
assert SIGNATURE_X_OFFSET_PT == 20    # факт: 0
```

**Причина:** В overlay.py явный комментарий: `0 = подпись начинается точно от левого края подчёркивания (после trim белых полей PNG)`. После v1.13 (предобработка подписи с crop по alpha) сдвиг 20pt стал лишним. Обоснованное изменение.

**Фикс теста:** обновить значение на 0.

### Падение 3: `test_signature_processor.py::test_downscale_preserves_aspect`

```python
expected_aspect = 1200/400  # = 3.0
# реальность: aspect ≈ 7.23
```

**Причина:** `_make_signature_png(1200, 400)` рисует **полосу чернил в средней трети** (от y=133 до y=266). `process_signature` крепит результат по bbox чернил → итог ~1200×133, downscale → 600×66 → aspect ≈ 9. Тест сравнивает aspect картинки vs aspect bbox чернил — разные вещи.

**Фикс теста:** считать ожидаемый aspect от **bbox чернил**, а не от исходной картинки. Или сделать "подпись" на всю высоту картинки.

---

## ШАГ 1 — Исправить 3 падающих теста

### Файл: `tests/test_dedup.py`

#### Тест 1 — починка

```python
def test_step1_different_bbox_kept():
    """Разные bbox + разный text → оба сохраняются (Шаг 1, exact bbox)."""
    a1 = _a("Lessor signature", "1", bbox=(50.0, 100.0, 200.0, 115.0))
    a2 = _a("Lessee signature", "1", bbox=(50.0, 200.0, 200.0, 215.0))
    result = dedup_anchors([a1, a2])
    assert len(result) == 2
```

Текст разный → не схлопывается Шагом 2 → оба остаются.

### Файл: `tests/test_overlay.py`

#### Тест 2 — починка

```python
def test_signature_x_offset_pt_constant():
    """SIGNATURE_X_OFFSET_PT == 0 (после v1.13 crop по alpha)."""
    assert SIGNATURE_X_OFFSET_PT == 0
```

### Файл: `tests/test_signature_processor.py`

#### Тест 3 — починка

```python
def test_downscale_preserves_aspect():
    """Пропорции bbox чернил сохраняются при уменьшении."""
    png = _make_signature_png(width=1200, height=400)
    result = process_signature(png)
    # _make_signature_png рисует чернила только в средней трети по Y.
    # Сравниваем aspect ИТОГОВОГО PNG с aspect BBOX ЧЕРНИЛ, не исходника.
    bx, by, bw, bh = result.bbox_original
    expected_aspect = bw / bh if bh > 0 else 1.0
    out_w, out_h = result.output_size
    actual_aspect = out_w / out_h if out_h > 0 else 0
    # Допуск 5% — округление при downscale до 600px
    assert abs(actual_aspect - expected_aspect) / expected_aspect < 0.05
```

---

## ШАГ 2 — Новые тесты под v1.18.x

### Новый файл: `tests/test_signer_profiles.py`

Тесты для Модели Б (v1.18.3): `list_signer_profiles`, `load_signer_profile_by_id`,
`detect_signer_profile`, составной язык в `get_aliases_for_language`.

```python
"""Тесты профилей подписантов (v1.18.3-v1.18.5)."""
from __future__ import annotations

import pytest

from signfinder.pipeline.settings import (
    detect_signer_profile,
    get_aliases_for_language,
    list_signer_profiles,
    load_signer_profile_by_id,
)


# ── Фикстура с двумя профилями ───────────────────────────────────────────────

@pytest.fixture
def storage_with_profiles(local_storage):
    """Storage с двумя профилями: default (Лебедев) и borisov (Innowise)."""
    local_storage.write_json("signers/default/profile.json", {
        "id": "default",
        "display": "Лебедев / Инлайн технолоджис",
        "match_markers": ["Инлайн технолоджис", "Лебедев"],
        "company_aliases": [
            {"language": "ru", "value": "ООО Инлайн технолоджис"},
        ],
        "signer_aliases": [
            {"language": "ru", "value": "Лебедев А.П."},
        ],
    })
    local_storage.write_json("signers/borisov/profile.json", {
        "id": "borisov",
        "display": "Vadim Borisov / Innowise",
        "match_markers": ["Innowise", "Vadim Borisov", "Вадим Борисов"],
        "company_aliases": [
            {"language": "en", "value": "Innowise Sp. z o.o"},
            {"language": "pl", "value": "Innowise Sp. z o.o"},
            {"language": "mk", "value": "Innowise"},
        ],
        "signer_aliases": [
            {"language": "en", "value": "Vadim Borisov"},
            {"language": "mk", "value": "Вадим Борисов"},
        ],
    })
    return local_storage


# ── list_signer_profiles ─────────────────────────────────────────────────────

def test_list_signer_profiles_returns_all(storage_with_profiles):
    profiles = list_signer_profiles(storage_with_profiles)
    ids = {p["id"] for p in profiles}
    assert ids == {"default", "borisov"}


def test_list_signer_profiles_empty_storage(local_storage):
    assert list_signer_profiles(local_storage) == []


def test_list_signer_profiles_none_storage():
    assert list_signer_profiles(None) == []


# ── load_signer_profile_by_id ────────────────────────────────────────────────

def test_load_profile_by_id_existing(storage_with_profiles):
    p = load_signer_profile_by_id(storage_with_profiles, "borisov")
    assert p["id"] == "borisov"
    assert "Innowise" in p["match_markers"]


def test_load_profile_missing_returns_empty(storage_with_profiles):
    p = load_signer_profile_by_id(storage_with_profiles, "nonexistent")
    assert p["id"] == "nonexistent"
    assert p["company_aliases"] == []


def test_load_default_legacy_fallback(local_storage):
    """default читается из корневого signer_profile.json если нет signers/default/."""
    local_storage.write_json("signer_profile.json", {
        "company_aliases": [{"language": "ru", "value": "Legacy Co"}],
        "signer_aliases": [{"language": "ru", "value": "Legacy Signer"}],
    })
    p = load_signer_profile_by_id(local_storage, "default")
    assert p["id"] == "default"
    assert any("Legacy Co" in a["value"] for a in p["company_aliases"])


# ── detect_signer_profile (Модель Б) ─────────────────────────────────────────

def test_detect_innowise_document(storage_with_profiles):
    text = "This agreement is between ... and Innowise Sp. z o.o (d/b/a Innowise Group) ..."
    assert detect_signer_profile(storage_with_profiles, text) == "borisov"


def test_detect_russian_document(storage_with_profiles):
    text = "Договор между ООО Инлайн технолоджис в лице Лебедева А.П. и ..."
    assert detect_signer_profile(storage_with_profiles, text) == "default"


def test_detect_unknown_falls_back_to_default(storage_with_profiles):
    """Документ без известных маркеров → default."""
    text = "Some unrelated document about cats and dogs."
    assert detect_signer_profile(storage_with_profiles, text) == "default"


def test_detect_no_profiles_returns_default(local_storage):
    """Нет профилей → возврат default_id."""
    assert detect_signer_profile(local_storage, "any text") == "default"


def test_detect_macedonian_cyrillic_borisov(storage_with_profiles):
    """Македонский текст с 'Вадим Борисов' → borisov."""
    text = "Договорот е помеѓу ... и Innowise со потпис Вадим Борисов."
    assert detect_signer_profile(storage_with_profiles, text) == "borisov"


# ── get_aliases_for_language: составной язык ─────────────────────────────────

def test_aliases_single_language(storage_with_profiles):
    """Одиночный язык: только en алиасы для borisov."""
    aliases = get_aliases_for_language(storage_with_profiles, "en", signer_id="borisov")
    assert "Innowise Sp. z o.o" in aliases["company"]
    assert "Vadim Borisov" in aliases["signer"]
    # Македонские не попадают
    assert "Вадим Борисов" not in aliases["signer"]


def test_aliases_composite_language_mk_en(storage_with_profiles):
    """Составной язык 'mk, en' → алиасы ОБОИХ языков (для dual-column)."""
    aliases = get_aliases_for_language(storage_with_profiles, "mk, en", signer_id="borisov")
    assert "Vadim Borisov" in aliases["signer"]
    assert "Вадим Борисов" in aliases["signer"]
    assert "Innowise Sp. z o.o" in aliases["company"]


def test_aliases_fallback_to_all_when_lang_unknown(storage_with_profiles):
    """Запрошен 'fr' (нет такого языка) → fallback на все алиасы."""
    aliases = get_aliases_for_language(storage_with_profiles, "fr", signer_id="borisov")
    # Все алиасы должны прийти fallback'ом
    assert len(aliases["signer"]) > 0
    assert len(aliases["company"]) > 0


def test_aliases_default_signer_id(storage_with_profiles):
    """Без указания signer_id → default."""
    aliases = get_aliases_for_language(storage_with_profiles, "ru")
    assert "ООО Инлайн технолоджис" in aliases["company"]
```

### Новый файл: `tests/test_parser_columns.py`

Тесты детектора колонок (v1.18.7).

```python
"""Тесты детектора колонок (v1.18.7) — Path A: одна страница, текст левая→правая."""
from __future__ import annotations

import io

import fitz
import pytest

from signfinder.pdf.parser import (
    ParsedDocument,
    _build_column_text,
    _detect_gutter,
    parse_pdf_bytes,
)


# ── _detect_gutter (детектор коридора) ───────────────────────────────────────

def _word_tuple(text: str, x0: float, y0: float, w: float = 50, h: float = 12) -> tuple:
    """Синтетический word-tuple в формате fitz get_text('words'): (x0,y0,x1,y1,text,...)."""
    return (x0, y0, x0 + w, y0 + h, text, 0, 0, 0)


def test_detect_gutter_two_columns():
    """Слова на x=50 и x=350 при ширине 595 → коридор найден в зоне 35-65%."""
    words = []
    # левая колонка
    for y in range(100, 700, 20):
        words.append(_word_tuple("left", 50, y, w=80))
    # правая колонка
    for y in range(100, 700, 20):
        words.append(_word_tuple("right", 350, y, w=80))
    cut = _detect_gutter(words, page_width=595)
    assert cut is not None
    assert 250 <= cut <= 350


def test_detect_gutter_single_column():
    """Слова распределены по всей ширине → коридор НЕ найден."""
    words = []
    for y in range(100, 700, 20):
        # слово пересекает зону 35-65%
        words.append(_word_tuple("wide text spans middle", 80, y, w=400))
    cut = _detect_gutter(words, page_width=595)
    assert cut is None


def test_detect_gutter_empty_page():
    assert _detect_gutter([], page_width=595) is None


# ── _build_column_text — упорядоченное чтение колонки ────────────────────────

def test_build_column_text_left():
    """Слова с x1 ≤ cut попадают в левую колонку."""
    words = [
        _word_tuple("Hello", 50, 100),       # x1=100, в левой
        _word_tuple("World", 350, 100),      # x0=350, в правой
        _word_tuple("Foo", 50, 130),
    ]
    text = _build_column_text(words, x_max=250)
    assert "Hello" in text
    assert "Foo" in text
    assert "World" not in text


def test_build_column_text_right():
    """Слова с x0 ≥ cut попадают в правую колонку."""
    words = [
        _word_tuple("Hello", 50, 100),
        _word_tuple("World", 350, 100),
        _word_tuple("Bar", 350, 130),
    ]
    text = _build_column_text(words, x_min=250)
    assert "World" in text
    assert "Bar" in text
    assert "Hello" not in text


def test_build_column_text_preserves_line_order():
    """Слова сортируются по (top, x0) — строки сверху вниз, слова слева направо."""
    words = [
        _word_tuple("third", 50, 200),
        _word_tuple("first", 50, 100),
        _word_tuple("FIRST_RIGHT", 150, 100),
        _word_tuple("second", 50, 150),
    ]
    text = _build_column_text(words, x_max=300)
    lines = text.split("\n")
    assert lines[0] == "first FIRST_RIGHT"
    assert lines[1] == "second"
    assert lines[2] == "third"


# ── parse_pdf_bytes — интеграционный ─────────────────────────────────────────

def _make_dual_column_pdf() -> bytes:
    """PDF где левая половина — английский, правая — польский (симуляция bilingual)."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Левая колонка (английский) — x в 50-250
    for i, line in enumerate([
        "This agreement is between the parties",
        "for the supply of services described",
        "in the appendix below.",
        "Signed by the Contractor:",
    ]):
        page.insert_text((50, 100 + i * 30), line, fontsize=10)
    # Правая колонка (польский) — x в 320-560
    for i, line in enumerate([
        "Niniejsza umowa jest zawierana",
        "pomiedzy stronami w celu",
        "swiadczenia opisanych uslug.",
        "Podpisano przez Wykonawce:",
    ]):
        page.insert_text((320, 100 + i * 30), line, fontsize=10)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_parse_pdf_detects_dual_column():
    """Двухколоночный PDF → layout=dual_column_vertical, languages = 2 элемента."""
    pdf = _make_dual_column_pdf()
    doc = parse_pdf_bytes(pdf, filename="test.pdf")
    assert doc.layout == "dual_column_vertical"
    assert doc.gutter_x is not None
    assert len(doc.pages) == 1
    assert doc.pages[0].layout == "dual_column_vertical"
    assert len(doc.pages[0].languages) >= 1


def test_parse_pdf_text_ordered_by_columns():
    """Текст dual-column PDF: сначала левая колонка целиком, потом разделитель, потом правая."""
    pdf = _make_dual_column_pdf()
    doc = parse_pdf_bytes(pdf, filename="test.pdf")
    text = doc.pages[0].text
    # Английский (левая) должен идти ДО разделителя "---"
    en_pos = text.find("This agreement")
    sep_pos = text.find("---")
    pl_pos = text.find("Niniejsza")
    assert 0 <= en_pos < sep_pos < pl_pos


def test_parse_pdf_single_column(pdf_bytes):
    """Стандартный одноколоночный PDF (из фикстуры) → layout=single_column."""
    doc = parse_pdf_bytes(pdf_bytes, filename="test.pdf")
    assert doc.layout == "single_column"
    assert doc.gutter_x is None


def test_parsed_document_has_languages_list(pdf_bytes):
    """ParsedDocument имеет поле languages (даже для одноязычного — список из 1)."""
    doc = parse_pdf_bytes(pdf_bytes, filename="test.pdf")
    assert isinstance(doc.languages, list)
    assert len(doc.languages) >= 1
```

### Дополнение в `tests/test_dedup.py` — dual-column

В конец файла добавить:

```python
# ── Dedup для dual-column (v1.18.7) ──────────────────────────────────────────

def test_dual_column_same_text_different_x_kept():
    """'Vadim Borisov' в левой колонке (x=50) и правой (x=350) → ОБА остаются.

    Регрессионный тест: в EN+PL документах одинаковый текст в двух колонках
    не должен схлопываться (фикс x_bucket в Шаге 2)."""
    left  = _a("Vadim Borisov", "1", bbox=(50.0, 600.0, 200.0, 615.0))
    right = _a("Vadim Borisov", "1", bbox=(350.0, 600.0, 500.0, 615.0))
    result = dedup_anchors([left, right])
    assert len(result) == 2


def test_dual_column_dups_within_column_dedup():
    """Два 'Borisov' в ОДНОЙ колонке (x≈50, разный y) → схлопываются."""
    a1 = _a("Borisov", "1", bbox=(50.0, 600.0, 200.0, 615.0))
    a2 = _a("Borisov", "1", bbox=(60.0, 700.0, 210.0, 715.0))   # тот же x_bucket
    result = dedup_anchors([a1, a2])
    assert len(result) == 1
```

---

## ШАГ 3 — Bump + проверка

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.18.20: fix failing tests + new tests for v1.18.x (profiles, columns, dual-column dedup)"
git push origin main
```

Bump core `__init__.py` + `pyproject.toml` → 1.18.20.

```powershell
cd C:\work\SignPDFMVPLocal
docker compose build api    # без --no-cache, только код-слой
docker compose up -d --force-recreate api
docker compose exec api pytest /app/sf_tests -q
```

Ожидаемый результат:
```
====== N passed in X.Xs ======
```
Где N = 88 (старые) + 21 (новые: 13 в test_signer_profiles, 6 в test_parser_columns, 2 в test_dedup) = **109**.

Все падающие тесты починены, новые добавлены. Если что-то падает — это **новые регрессии**, разбираем точечно.

---

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
Делать по шагам: сначала 3 падающих теста (быстрая проверка `pytest` → 88 passed),
потом 2 новых файла + дополнение dedup → `pytest` снова.
