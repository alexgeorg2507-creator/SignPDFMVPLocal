# SignFinder v1.18.1 — Человекочитаемые имена шаблонов

Прочитай `C:\work\CLAUDE.md` перед началом.

Изменения только в signfinder-core. Задача: сделать имена шаблонов
информативными для оператора.

Сейчас: `pipelineAuto1_2026-06-05_1134_ru` — нечитаемо.
Нужно: `Договор аренды с ООО Ромашка ru (08.06.2026)` — на языке договора.

---

## Корень проблемы

`generate_template_name` в `templates/storage.py` имеет поле `doc_type` в synonyms,
но оно НИКОГДА не заполняется. В `save_pipeline_template` (auto1.py) в `synonyms_used`
кладут только нашу сторону (legal_entity/roles/signer). Контрагент и тип — нет.

При этом всё необходимое уже есть:
- Тип договора — regex по заголовку первой страницы (детерминированно, бесплатно)
- Контрагент — в `our_side["all_parties"]` (стороны, которые не наша)
- Язык — параметр

---

## Файл 1 — `signfinder-core/signfinder/pipeline/auto1.py`

### 1.1 Добавить функцию `_extract_contract_type`

Поместить рядом с другими _helper-функциями (после `_signer_underscore_patterns`):

```python
def _extract_contract_type(doc: ParsedDocument, language: str) -> str:
    """Детерминированное извлечение типа договора из заголовка первой страницы.

    Работает без LLM по regex — бесплатно и надёжно для структурированных заголовков.
    Пример: 'ДОГОВОР АРЕНДЫ №...' → 'Договор аренды'
    """
    import re as _re
    text = ""
    if doc.pages:
        text = (doc.pages[0].text or "")[:800]

    if language == "ru":
        # Ищем "ДОГОВОР [ЧТО-ТО]" — тип в 1-4 слова после слова ДОГОВОР
        m = _re.search(
            r"ДОГОВОР\s+((?:[А-ЯЁА-яёa-z][А-ЯЁА-яёa-z\-]*\s+){0,3}[А-ЯЁА-яёa-z][А-ЯЁА-яёa-z\-]*)",
            text,
            _re.IGNORECASE,
        )
        if m:
            raw = m.group(1).strip()
            # Убираем типичный мусор: номер, дата, "№", "N"
            raw = _re.sub(r"\s*[№NnNnNn]?\s*\d.*$", "", raw).strip()
            raw = _re.sub(r"\s*(от|г\.|года).*$", "", raw, flags=_re.IGNORECASE).strip()
            if 2 <= len(raw.split()) <= 5:
                return "Договор " + raw.lower()
        if _re.search(r"договор", text, _re.IGNORECASE):
            return "Договор"
        return "Договор"

    elif language == "en":
        m = _re.search(
            r"(SERVICE\s+AGREEMENT|SUPPLY\s+AGREEMENT|LEASE\s+AGREEMENT|"
            r"CONTRACT\s+FOR\s+[A-Z][A-Za-z\s]{2,25}|AGREEMENT\s+(?:FOR|ON|OF)\s+[A-Z][A-Za-z\s]{2,25})",
            text, _re.IGNORECASE,
        )
        if m:
            return m.group(0).strip()[:50].title()
        return "Contract"

    elif language == "pl":
        m = _re.search(
            r"(UMOWA\s+(?:[A-ZŁĄĆĘÓŚŻŹ][A-ZŁĄĆĘÓŚŻŹa-złąćęóśżź\-]*\s+){0,3}"
            r"[A-ZŁĄĆĘÓŚŻŹ][A-ZŁĄĆĘÓŚŻŹa-złąćęóśżź\-]*)",
            text, _re.IGNORECASE,
        )
        if m:
            raw = m.group(1).strip()
            raw = _re.sub(r"\s*[nrNR]?\s*\d.*$", "", raw).strip()
            if 1 <= len(raw.split()) <= 5:
                return raw.capitalize()
        return "Umowa"

    return "Договор"
```

### 1.2 Добавить функцию `_extract_counterparty`

```python
def _extract_counterparty(our_side: dict) -> str:
    """Извлечь название контрагента (другой стороны) из all_parties.

    Возвращает legal_entity контрагента или его роль если legal_entity нет.
    Пустая строка если контрагент не определён.
    """
    our_entity = (our_side.get("legal_entity") or "").strip().lower()
    our_roles = {r.strip().lower() for r in (our_side.get("roles") or []) if r}

    for p in (our_side.get("all_parties") or []):
        if not isinstance(p, dict):
            continue
        le = (p.get("legal_entity") or "").strip()
        role = (p.get("role") or "").strip()
        # Пропускаем нашу сторону
        if le and le.lower() == our_entity:
            continue
        if role and role.lower() in our_roles:
            continue
        # Нашли другую сторону
        if le:
            return le  # предпочитаем legal_entity ("ООО Ромашка")
        if role:
            return role  # fallback на роль ("Заказчик")

    return ""
```

### 1.3 Обновить `save_pipeline_template` — добавить contract_type и counterparty

В функции `save_pipeline_template`, перед строкой `synonyms_used = {...}`,
добавить извлечение типа и контрагента:

```python
# Извлечь тип договора и контрагента для читаемого имени шаблона
contract_type = _extract_contract_type(doc, language)
counterparty = _extract_counterparty(our_side)

synonyms_used = {
    "legal_entity": our_side.get("legal_entity", ""),
    "roles": our_side.get("roles", []),
    "signer": our_side.get("signer", ""),
    "contract_type": contract_type,       # ← новое
    "counterparty": counterparty,         # ← новое
}
```

---

## Файл 2 — `signfinder-core/signfinder/templates/storage.py`

### 2.1 Обновить `generate_template_name`

Полная замена функции:

```python
def generate_template_name(language: str, synonyms: Optional[dict] = None) -> str:
    """Формирует читаемое имя шаблона.

    Формат: "{тип договора} с {контрагент} {lang} ({дата})"
    Пример: "Договор аренды с ООО Ромашка ru (08.06.2026)"

    Если контрагент неизвестен: "Договор аренды ru (08.06.2026)"
    Если тип неизвестен:       "Договор с ООО Ромашка ru (08.06.2026)"
    Fallback (нет synonyms):   "Договор ru (08.06.2026)"
    """
    date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    synonyms = synonyms or {}

    contract_type = (synonyms.get("contract_type") or "").strip()
    counterparty = (synonyms.get("counterparty") or "").strip()

    # Fallback: старое поле doc_type / legal_entity для обратной совместимости
    if not contract_type:
        contract_type = (synonyms.get("doc_type") or "Договор").strip()

    # Ограничить длину компонентов
    contract_type = contract_type[:50]
    counterparty = counterparty[:40]

    if counterparty:
        name = f"{contract_type} с {counterparty} {language} ({date_str})"
    else:
        name = f"{contract_type} {language} ({date_str})"

    # Итоговое ограничение длины (имя хранится в JSON, не в файловой системе)
    return name[:100]
```

---

## Bump + деплой

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.18.1: human-readable template names (contract type + counterparty)"
git push origin main

cd C:\work\SignPDFMVPLocal
docker compose build --no-cache api
docker compose up -d --force-recreate api
docker compose logs api 2>&1 | Select-Object -First 5
```

Bump: core `__init__.py` + `pyproject.toml` → 1.18.1, CLAUDE.md.

---

## Тест

1. Прогнать analyze + «Сохранить как шаблон» на тестовом договоре.
2. Настройки → Шаблоны → имя должно быть читаемым:
   - `Договор аренды с ООО Лебедев Инжиниринг ru (08.06.2026)` — ОК
   - `Договор оказания услуг ru (08.06.2026)` — если контрагент не определён — ОК
   - Длина ≤ 100 символов
3. Старые шаблоны (с именем pipelineAuto1_...) — не трогать, они хранятся как есть.

---

## ВАЖНО: Что НЕ меняется

- Имена существующих шаблонов не переименовываются (нет миграции).
- template_id (uuid) не меняется — файл хранится под template_id.json, не под именем.
- Имя при ручном сохранении через UI (поле «Название шаблона») — не затронуто;
  оператор может написать что угодно, это отдельный path через template_name параметр.
- Обратная совместимость через fallback на старые поля (doc_type).

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
