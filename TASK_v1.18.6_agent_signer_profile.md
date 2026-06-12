# SignFinder v1.18.6 — Агент: автовыбор профиля подписанта

Прочитай `C:\work\CLAUDE.md` перед началом.
Изменения только в одном файле:
`C:\work\SignPDFMVPLocal\agent\app\processor.py`

Деплой: только agent.

---

## Контекст

После v1.18.3-v1.18.5:
- core определяет профиль по тексту документа → кладёт detected_signer_id в AnalysisResult
- api возвращает detected_signer_id в AnalysisResponse
- Агент сейчас всегда подписывает константой SIGNER_ID="default" из env

Задача: агент берёт detected_signer_id из ответа analyze и передаёт его в sign.
Fallback — SIGNER_ID из config (как сейчас).

---

## Изменение 1 — `_api_sign`: добавить параметр signer_id

Было:
```python
def _api_sign(pdf_bytes: bytes, anchors: list, filename: str) -> bytes:
    import json
    url = f"{SIGNFINDER_API_URL}/v1/sign"
    with httpx.Client(timeout=_TIMEOUT_SIGN) as c:
        resp = c.post(
            url, headers=_API_HEADERS,
            files={"file": (filename, pdf_bytes, "application/pdf")},
            data={"anchors_json": json.dumps(anchors), "signer_id": SIGNER_ID, "signature_scale": "1.0"},
        )
        resp.raise_for_status()
    return resp.content
```

Стало:
```python
def _api_sign(pdf_bytes: bytes, anchors: list, filename: str,
              signer_id: str = SIGNER_ID) -> bytes:
    import json
    url = f"{SIGNFINDER_API_URL}/v1/sign"
    with httpx.Client(timeout=_TIMEOUT_SIGN) as c:
        resp = c.post(
            url, headers=_API_HEADERS,
            files={"file": (filename, pdf_bytes, "application/pdf")},
            data={"anchors_json": json.dumps(anchors),
                  "signer_id": signer_id, "signature_scale": "1.0"},
        )
        resp.raise_for_status()
    return resp.content
```

---

## Изменение 2 — `process_message`: взять detected_signer_id из analyze

Найти в функции `process_message` блок где вызывается `_api_analyze` и `_api_sign`:

Было:
```python
            analysis = _api_analyze(pdf_bytes, pdf_name)
            light = analysis.get("traffic_light", "no_match")
            mt = analysis.get("matched_template") or {}
            anchors = analysis.get("anchors") or []

            signed_pdf: Optional[bytes] = None
            if light != "no_match" and anchors:
                try:
                    logger.info("uid=%s: sign %s (%d anchors)", uid, pdf_name, len(anchors))
                    signed_pdf = _api_sign(pdf_bytes, anchors, pdf_name)
```

Стало:
```python
            analysis = _api_analyze(pdf_bytes, pdf_name)
            light = analysis.get("traffic_light", "no_match")
            mt = analysis.get("matched_template") or {}
            anchors = analysis.get("anchors") or []
            detected_signer = analysis.get("detected_signer_id") or SIGNER_ID

            signed_pdf: Optional[bytes] = None
            if light != "no_match" and anchors:
                try:
                    logger.info("uid=%s: sign %s (%d anchors) signer=%s",
                                uid, pdf_name, len(anchors), detected_signer)
                    signed_pdf = _api_sign(pdf_bytes, anchors, pdf_name,
                                          signer_id=detected_signer)
```

---

## Деплой

```powershell
cd C:\work\SignPDFMVPLocal
docker compose build agent
docker compose up -d --force-recreate agent
docker compose logs agent --tail 20
```

Только agent — api/streamlit/core не трогаем.

---

## Тест

1. Отправить тестовое письмо с Innowise-документом на SignfinderIn
2. В логе агента ждём строку:
   `uid=...: sign ... signer=borisov`
   (не signer=default)
3. Подписанный PDF в письме — подпись Borisov (не Лебедева)
4. Русский договор → signer=default (регрессия)

Если detected_signer_id не вернулся (old document, старый кэш) — агент корректно
fallback'ает на SIGNER_ID="default". Тихий graceful degradation.

---

## Что НЕ делается здесь

- Сохранение detected_signer_id в queue_index / журнал (полезно, но не срочно)
- resign_item использует SIGNER_ID (fallback, для ручного переподписания это ок)
- Колонки (отдельное направление)

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
