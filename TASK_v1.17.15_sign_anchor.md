# SignFinder v1.17.15 — Фикс 422 на /v1/sign (неполный TextAnchor)

Прочитай `C:\work\CLAUDE.md` перед началом.

---

## Баг (найден точно)

`/v1/sign` возвращает 422 на КАЖДОМ запросе агента. detail:
```
422 {"detail":"Невалидный якорь {...}: ..."}
```

Подпись не накладывается → письма агента приходят без вложений.

## Корень

`TextAnchor` (signfinder-core/signfinder/anchors/models.py) — dataclass с **13
обязательными полями** (без дефолтов):
```
id, anchor_type, anchor_level, anchor_text, position, offset_pt,
generated_pattern, context_before, context_after, page_hint, added_by,
added_at, bbox
```

А `/v1/sign` в `signfinder-api/app/routers/pipeline.py` строит его из **8 полей**:
```python
TextAnchor(
    id=..., anchor_level=..., anchor_text=..., position=...,
    generated_pattern=..., bbox=..., added_by=..., page_hint=...,
)
```

Не хватает: `anchor_type`, `offset_pt`, `context_before`, `context_after`, `added_at`.
→ `TypeError: missing required arguments` → ловится в except → `422 Невалидный якорь`.

(analyze отдаёт якоря с 8 полями, sign не дозаполняет недостающие.)

## Фикс — дозаполнить недостающие поля при построении TextAnchor

В `pipeline.py`, в endpoint `sign_document`, заменить блок построения
`anchor_objects` на версию с дефолтами для всех 13 полей:

```python
from signfinder.anchors import TextAnchor
from datetime import datetime, timezone

anchor_objects = []
for a in anchors:
    try:
        bbox = a.get("bbox", [0, 0, 100, 20])
        anchor_objects.append(TextAnchor(
            id=a.get("id", "a0"),
            anchor_type=a.get("anchor_type", "text_proximity"),
            anchor_level=a.get("anchor_level", 1),
            anchor_text=a.get("anchor_text", ""),
            position=a.get("position", "below"),
            offset_pt=a.get("offset_pt", 0.0),
            generated_pattern=a.get("generated_pattern", ""),
            context_before=a.get("context_before", ""),
            context_after=a.get("context_after", ""),
            page_hint=str(a.get("page_hint", "0")),
            added_by=a.get("added_by", "manual_click"),
            added_at=a.get("added_at", datetime.now(timezone.utc).isoformat()),
            bbox=tuple(bbox),
        ))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Невалидный якорь {a}: {e}")
```

Ключевое: добавлены `anchor_type`, `offset_pt`, `context_before`, `context_after`,
`added_at` с разумными дефолтами. `position` валиден (Literal включает "on").

## Проверка значений position

`TextAnchor.position` = Literal["right","left","below","above","on"]. analyze
отдаёт "on" — это валидное значение, дефолт "below" только если поля нет.
НЕ менять Literal.

## Bump + деплой (только API, core не трогаем)

```powershell
cd C:\work\SignPDFMVPLocal
docker compose build api
docker compose up -d --force-recreate api
docker compose logs api 2>&1 | Select-Object -First 5
```

Версия API → 1.17.15 в main.py.
(signfinder-core НЕ менялся — git push не нужен, --no-cache не нужен.)

## Тест

1. Из контейнера агента — точечный sign на реальном PDF:
```powershell
docker compose exec agent python -c "import httpx,os,json; key=os.environ.get('SIGNFINDER_API_KEY',''); pdf=open('/data/agent/pdfs/originals/1/Contract_Support.pdf','rb').read(); a=httpx.post('http://api:8000/v1/analyze',headers={'Authorization':f'Bearer {key}'},files={'file':('c.pdf',pdf,'application/pdf')},timeout=180).json(); anc=a.get('anchors',[]); r=httpx.post('http://api:8000/v1/sign',headers={'Authorization':f'Bearer {key}'},files={'file':('c.pdf',pdf,'application/pdf')},data={'anchors_json':json.dumps(anc),'signer_id':'default','signature_scale':'1.0'},timeout=60); print('sign:', r.status_code, len(r.content), 'bytes')"
```
Ожидаем: `sign: 200 <много> bytes` (подписанный PDF).

2. Снять «прочитано» с письма в SignfinderIn → опросить
3. В SignfinderYellow/Green письмо С подписанным PDF во вложении
4. Журнал: документ обработан, светофор корректный

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
