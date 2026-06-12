"""Обработка одного IntakeMessage: extract → analyze → sign → route.

Вызывает signfinder-api по HTTP. Не дублирует бизнес-логику из core.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from app.config import (
    FOLDER_GREEN,
    FOLDER_RED,
    FOLDER_YELLOW,
    ORIGINALS_DIR,
    SIGNED_DIR,
    SIGNFINDER_API_KEY,
    SIGNFINDER_API_URL,
    SIGNER_ID,
)

logger = logging.getLogger(__name__)

_API_HEADERS = {"Authorization": f"Bearer {SIGNFINDER_API_KEY}"}
_TIMEOUT_ANALYZE = httpx.Timeout(180.0)
_TIMEOUT_SIGN = httpx.Timeout(60.0)


@dataclass
class DocResult:
    name: str
    original_name: str
    light: str
    template: str
    score: Optional[float]
    anchor_count: int
    anchors: list = field(default_factory=list)
    signed_pdf: Optional[bytes] = None
    error: Optional[str] = None


@dataclass
class ProcessingResult:
    uid: str
    subject: str
    sender: str
    destination_folder: str
    docs: list[DocResult] = field(default_factory=list)
    error: Optional[str] = None


def _api_analyze(pdf_bytes: bytes, filename: str) -> dict:
    url = f"{SIGNFINDER_API_URL}/v1/analyze"
    with httpx.Client(timeout=_TIMEOUT_ANALYZE) as c:
        resp = c.post(url, headers=_API_HEADERS,
                      files={"file": (filename, pdf_bytes, "application/pdf")})
        resp.raise_for_status()
    return resp.json()


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


def _docx_to_pdf(docx_bytes: bytes, original_name: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = Path(tmpdir) / "input.docx"
        docx_path.write_bytes(docx_bytes)
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", tmpdir, str(docx_path)],
            check=True, capture_output=True, timeout=120,
        )
        pdf_path = Path(tmpdir) / "input.pdf"
        if not pdf_path.exists():
            raise RuntimeError("LibreOffice не создал PDF")
        return pdf_path.read_bytes()


def _safe_slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:80]


def _save_original(uid: str, filename: str, pdf_bytes: bytes) -> None:
    uid_dir = os.path.join(ORIGINALS_DIR, uid)
    os.makedirs(uid_dir, exist_ok=True)
    with open(os.path.join(uid_dir, _safe_slug(filename)), "wb") as f:
        f.write(pdf_bytes)


def _save_signed(uid: str, filename: str, pdf_bytes: bytes) -> None:
    uid_dir = os.path.join(SIGNED_DIR, uid)
    os.makedirs(uid_dir, exist_ok=True)
    with open(os.path.join(uid_dir, _safe_slug(filename)), "wb") as f:
        f.write(pdf_bytes)


def _load_originals(uid: str) -> list[tuple[str, bytes]]:
    uid_dir = os.path.join(ORIGINALS_DIR, uid)
    if not os.path.isdir(uid_dir):
        return []
    result = []
    for fname in sorted(os.listdir(uid_dir)):
        fpath = os.path.join(uid_dir, fname)
        try:
            with open(fpath, "rb") as f:
                result.append((fname, f.read()))
        except Exception as e:
            logger.error("load_originals uid=%s fname=%s: %s", uid, fname, e)
    return result


def process_message(msg) -> ProcessingResult:
    uid = msg.uid
    subject = msg.subject
    sender = msg.sender

    pdf_attachments = [a for a in msg.attachments if a.filename.lower().endswith((".pdf", ".docx"))]
    if not pdf_attachments:
        logger.info("uid=%s: no PDF/DOCX attachments → Red", uid)
        return ProcessingResult(uid=uid, subject=subject, sender=sender,
                                destination_folder=FOLDER_RED, error="Нет PDF/DOCX вложений")

    docs: list[DocResult] = []

    for att in pdf_attachments:
        fname = att.filename
        try:
            if fname.lower().endswith(".docx"):
                logger.info("uid=%s: converting %s DOCX→PDF", uid, fname)
                pdf_bytes = _docx_to_pdf(att.content, fname)
                pdf_name = fname.rsplit(".", 1)[0] + ".pdf"
            else:
                pdf_bytes = att.content
                pdf_name = fname

            _save_original(uid, pdf_name, pdf_bytes)

            logger.info("uid=%s: analyze %s", uid, pdf_name)
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
                    _save_signed(uid, pdf_name, signed_pdf)
                except Exception as e:
                    logger.error("uid=%s: sign %s failed: %s", uid, pdf_name, e)
                    light = "yellow"

            docs.append(DocResult(
                name=pdf_name, original_name=fname, light=light,
                template=mt.get("best_match_template_id") or "",
                score=mt.get("best_match_score"), anchor_count=len(anchors),
                anchors=anchors, signed_pdf=signed_pdf, error=analysis.get("error"),
            ))

        except Exception as e:
            logger.error("uid=%s: error processing %s: %s", uid, fname, e)
            docs.append(DocResult(name=fname, original_name=fname, light="no_match",
                                  template="", score=None, anchor_count=0, error=str(e)))

    destination = _determine_destination(docs)
    logger.info("uid=%s: destination=%s docs=%d", uid, destination, len(docs))
    return ProcessingResult(uid=uid, subject=subject, sender=sender,
                            destination_folder=destination, docs=docs)


def _determine_destination(docs: list[DocResult]) -> str:
    lights = {d.light for d in docs}
    if "no_match" in lights:
        processed = [d for d in docs if d.light != "no_match"]
        return FOLDER_YELLOW if processed else FOLDER_RED
    if "yellow" in lights:
        return FOLDER_YELLOW
    return FOLDER_GREEN


def resign_item(uid: str, item: dict, new_anchors: list | None = None) -> list[tuple[str, bytes]]:
    originals = _load_originals(uid)
    if not originals:
        raise RuntimeError(f"Оригиналы для uid={uid} не найдены")

    results = []
    docs = item.get("documents", [])

    for fname, pdf_bytes in originals:
        anchors = new_anchors
        if not anchors:
            stored_doc = next((d for d in docs if d.get("name") == fname), None)
            anchors = (stored_doc or {}).get("anchors") or []
        if not anchors:
            logger.warning("resign uid=%s fname=%s: no anchors, skipping", uid, fname)
            continue
        try:
            signed = _api_sign(pdf_bytes, anchors, fname)
            _save_signed(uid, fname, signed)
            results.append((fname, signed))
        except Exception as e:
            logger.error("resign uid=%s fname=%s: %s", uid, fname, e)

    return results


_LIGHT_LABEL = {
    "green": "🟢 Зелёный — подписано автоматически",
    "yellow": "🟡 Жёлтый — требует проверки оператором",
    "no_match": "🔴 Ошибка обработки",
}


def build_email_body(subject: str, docs: list[DocResult]) -> str:
    lines = [f'SignFinder обработал документы из письма "{subject}".\n']
    for doc in docs:
        pct = f" ({int(doc.score * 100)}%)" if doc.score is not None else ""
        tpl = f"Шаблон: {doc.template[:8]}…{pct}" if doc.template else "Шаблон: не найден"
        lines.append(f"📄 {doc.original_name}")
        lines.append(f"   {tpl}")
        lines.append(f"   Светофор: {_LIGHT_LABEL.get(doc.light, doc.light)}")
        if doc.anchor_count:
            lines.append(f"   Мест подписи: {doc.anchor_count}")
        if doc.error:
            lines.append(f"   ⚠️ {doc.error}")
        lines.append("")
    lines.append(f"Обработано: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    return "\n".join(lines)
