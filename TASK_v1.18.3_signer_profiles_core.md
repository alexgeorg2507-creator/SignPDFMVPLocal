# SignFinder v1.18.3 — Профили подписантов в core (фундамент Модели Б)

Прочитай `C:\work\CLAUDE.md` перед началом.
Изменения только в signfinder-core. Это фундамент мульти-подписанта.
Деплой: локальная версия в Docker (signfinder-core → git, --no-cache rebuild api).

---

## Контекст и решение

Сейчас подписант один: `signer_profile.json` (корень storage) с company_aliases /
signer_aliases. Подпись уже параметризована: `signers/{id}/signature.png`. То есть
подпись готова к мульти-, а профиль (синонимы) — нет. Полусделанный мульти-signer.

Задача: несколько профилей подписанта, каждый = синонимы + подпись + match_markers.
Автоопределение (Модель Б): по содержимому документа выбирается профиль.
Один активный за раз в документе (Вариант 1, не multi-signer-в-одном-документе).

Пример: документ с «Innowise / Vadim Borisov» → профиль borisov;
документ с «Инлайн технолоджис / Лебедев» → профиль lebedev.

---

## Часть 1 — Структура профиля

Профиль переезжает К подписи: `signers/{id}/profile.json` + `signers/{id}/signature.png`.

Формат `signers/{id}/profile.json`:
```json
{
  "id": "borisov",
  "display": "Vadim Borisov / Innowise",
  "match_markers": ["Innowise", "Vadim Borisov", "Вадим Борисов"],
  "company_aliases": [
    {"language": "en", "value": "Innowise Sp. z o.o, Innowise Group"},
    {"language": "pl", "value": "Innowise Sp. z o.o"},
    {"language": "mk", "value": "Innowise"}
  ],
  "signer_aliases": [
    {"language": "en", "value": "Vadim Borisov"},
    {"language": "mk", "value": "Вадим Борисов"},
    {"language": "pl", "value": "Vadim Borisov"}
  ],
  "updated_at": ""
}
```

`match_markers` — строки-признаки НАШЕЙ стороны в документе. По ним детектируется
профиль (наша сторона всегда присутствует — мы документ подписываем).

**ПРОВЕРЕНО на корпусе клиента (6 документов, июнь 2026):**
- «Innowise» — встречается во ВСЕХ 6 документах (формы: «Innowise Sp. z o.o»,
  «Innowise Group», «d/b/a Innowise Group»). Это ОСНОВНОЙ надёжный маркер.
- Рег.номер 520012851 и VAT PL1133041576 — только в 1 документе из 6.
  НЕ использовать как основу — детект провалится на 5 из 6. В маркеры НЕ кладём
  (или только слабым бонусом, без расчёта на них).
- Имя клиента бывает зачернено (redacted) — поэтому маркеры строим по НАШЕЙ
  стороне (Innowise/Borisov), не по контрагенту.

Принцип match_markers: короткое стабильное ядро названия нашей компании
(«Innowise», «Инлайн технолоджис») + имя подписанта как подстраховка. НЕ рег.номера,
НЕ VAT — они нестабильны по корпусу.

---

## Часть 2 — `signfinder-core/signfinder/pipeline/settings.py`

### 2.1 Новые функции для профилей (рядом с существующими signer_profile)

```python
_SIGNERS_PREFIX = "signers/"


def list_signer_profiles(storage) -> list[dict]:
    """Список всех профилей подписантов из signers/*/profile.json."""
    if storage is None:
        return []
    out = []
    try:
        keys = storage.list_prefix(_SIGNERS_PREFIX)
    except Exception:
        keys = []
    seen = set()
    for k in keys:
        # ищем signers/<id>/profile.json
        parts = k[len(_SIGNERS_PREFIX):].split("/")
        if len(parts) >= 2 and parts[1] == "profile.json":
            sid = parts[0]
            if sid in seen:
                continue
            seen.add(sid)
            data = storage.read_json(k)
            if data:
                data.setdefault("id", sid)
                out.append(data)
    return out


def load_signer_profile_by_id(storage, signer_id: str) -> dict:
    """Профиль по id. Fallback на legacy signer_profile.json (корень) для 'default'."""
    if storage is not None:
        data = storage.read_json(f"{_SIGNERS_PREFIX}{signer_id}/profile.json")
        if data:
            data.setdefault("id", signer_id)
            return data
    # legacy fallback: старый единственный signer_profile.json в корне
    if signer_id == "default":
        legacy = load_signer_profile(storage)  # существующая функция
        legacy.setdefault("id", "default")
        return legacy
    return {"id": signer_id, "company_aliases": [], "signer_aliases": [], "match_markers": []}


def detect_signer_profile(storage, doc_text: str, default_id: str = "default") -> str:
    """Автоопределение профиля по содержимому документа (Модель Б).

    Считает совпадения match_markers каждого профиля в тексте.
    Возвращает signer_id профиля с макс совпадениями. Fallback на default_id.

    Матч по подстроке, регистронезависимо. Маркеры — короткое ядро названия
    нашей компании (напр. 'innowise'), которое стабильно по всему корпусу клиента.
    """
    profiles = list_signer_profiles(storage)
    if not profiles:
        return default_id
    text_low = (doc_text or "").lower()
    best_id, best_score = default_id, 0
    for p in profiles:
        score = 0
        for marker in p.get("match_markers", []):
            m = (marker or "").strip().lower()
            if m and m in text_low:
                score += 1
        if score > best_score:
            best_score, best_id = score, p.get("id", default_id)
    return best_id
```

### 2.2 `get_aliases_for_language` — добавить параметр signer_id

```python
def get_aliases_for_language(storage, language: str, signer_id: str = "default") -> dict[str, list[str]]:
    """Алиасы {company, signer} для языка КОНКРЕТНОГО профиля.

    Раньше читал единственный signer_profile.json. Теперь — профиль по signer_id.
    """
    profile = load_signer_profile_by_id(storage, signer_id)
    lang = (language or "").lower()[:2]

    def _filter(key: str) -> list[str]:
        all_aliases = profile.get(key, [])
        by_lang = [a["value"] for a in all_aliases
                   if a.get("language") == lang and a.get("value", "").strip()]
        if by_lang:
            return by_lang
        return [a["value"] for a in all_aliases if a.get("value", "").strip()]

    return {"company": _filter("company_aliases"), "signer": _filter("signer_aliases")}
```

Сохрани обратную совместимость: вызов без signer_id → "default" (как раньше).

---

## Часть 3 — Фасад `signfinder/__init__.py` (SignFinder.analyze)

В методе `analyze` (или где вызывается pipeline) ДО step3:
1. Получить текст документа (первая страница + последняя — где обычно наша сторона)
2. `detected_id = detect_signer_profile(self.storage, doc_text)`
3. Передать `detected_id` в pipeline, чтобы `get_aliases_for_language` брал синонимы
   ЭТОГО профиля
4. Положить `detected_signer_id` в результат analyze (новое поле в AnalysisResult)

Если в pipeline (auto1.py) `get_aliases_for_language` вызывается — пробросить туда
signer_id определённого профиля.

Результат analyze должен содержать `detected_signer_id` — чтобы api/агент знали
какой подписью подписывать.

---

## Часть 4 — auto1.py: проброс signer_id

Где `get_aliases_for_language(storage, language)` вызывается в run_step3/run_pipeline_auto_1 —
добавить параметр signer_id (определённый профиль). Сигнатуру пайплайна расширить
опциональным `signer_id: str = "default"`.

---

## Часть 5 — Миграция (без потери русского профиля)

НЕ ломать существующего Лебедева. Текущий `signer_profile.json` (корень) остаётся
рабочим через legacy fallback в `load_signer_profile_by_id("default")`.

Дополнительно создать `signers/default/profile.json` из текущих данных + добавить
match_markers для русского клиента (короткое ядро названия + фамилия подписанта):
```json
{
  "id": "default",
  "display": "Лебедев / Инлайн технолоджис",
  "match_markers": ["Инлайн технолоджис", "Лебедев"],
  "company_aliases": [{"language":"ru","value":"Общество с ограниченной ответственностью «Инлайн технолоджис», Инлайн технолоджис, ООО «Инлайн технолоджис»"}],
  "signer_aliases": [{"language":"ru","value":"Лебедев, Лебедев А, Лебедев Алексей Петрович, Лебедев А.П., А.П. Лебедев"}]
}
```
(подпись signers/default/signature.png уже на месте — не трогать)

Профиль borisov НЕ создавать в этом промпте — это сделает оператор через UI (v1.18.5)
или вручную позже. Сейчас только механизм + миграция default.

---

## Bump + деплой

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.18.3: multi-signer profiles + content-based auto-detection (Model B)"
git push origin main

cd C:\work\SignPDFMVPLocal
docker compose build --no-cache api
docker compose up -d --force-recreate api
docker compose logs api 2>&1 | Select-Object -First 5
```

Bump: core `__init__.py` + `pyproject.toml` → 1.18.3, CLAUDE.md.

---

## Тест

1. Существующий русский договор (Лебедев/Инлайн) → analyze → detected_signer_id="default",
   синонимы Лебедева подхватываются (регрессия не сломана).
2. `list_signer_profiles` возвращает default.
3. `detect_signer_profile` на тексте с «Инлайн технолоджис» → "default".
4. `detect_signer_profile` на тексте без известных маркеров → "default" (fallback).
5. Юнит: создать тестовый signers/borisov/profile.json с match_markers=["Innowise"],
   detect на тексте с «Innowise» → "borisov".
6. Проверить на реальном Innowise-документе из C:\Users\User\Downloads\договора примеры\PL:
   "Innowise" находится во всех 6 → если есть профиль borisov, detect → "borisov".

## Что НЕ делается здесь

- API endpoints (v1.18.4)
- UI управления профилями (v1.18.5)
- Агент использует detected профиль (v1.18.6)
- parties.json — НЕ трогаем (мёртвый legacy, депрекейт отдельно)

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
