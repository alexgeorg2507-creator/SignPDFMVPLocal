"""Poll-loop: один цикл опроса SignfinderIn."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_state: dict = {
    "running": False,
    "last_poll": None,
    "last_poll_count": 0,
    "error": None,
    "queue_count": 0,
}


def get_poller_state() -> dict:
    from app.queue_index import load_queue
    state = dict(_state)
    try:
        state["queue_count"] = len(load_queue().get("items", []))
    except Exception:
        state["queue_count"] = -1
    return state


def run_one_poll() -> dict:
    global _state
    _state["running"] = True
    _state["error"] = None
    processed = 0
    errors = 0

    try:
        from app import mailbox, queue_index, activity_log
        from app.processor import process_message, build_email_body

        mailbox.ensure_all_folders()   # гарантировать все ярлыки до обработки

        messages = mailbox.poll_inbox()
        logger.info("poll: %d messages in In", len(messages))

        for msg in messages:
            try:
                result = process_message(msg)
                _route_result(result, mailbox, queue_index, activity_log)
                processed += 1
            except Exception as e:
                logger.exception("poll: error processing uid=%s: %s", msg.uid, e)
                errors += 1
                _state["error"] = str(e)
                try:
                    mailbox.move_to_archive(msg.uid)
                except Exception:
                    pass

    except Exception as e:
        logger.exception("poll: fatal: %s", e)
        _state["error"] = str(e)
    finally:
        _state["running"] = False
        _state["last_poll"] = _now()
        _state["last_poll_count"] = processed

    return {"processed": processed, "errors": errors}


def _route_result(result, mailbox, queue_index, activity_log) -> None:
    from app.config import load_mail_config
    cfg = load_mail_config()
    uid = result.uid
    dest = result.destination_folder

    signed_pdfs = [(d.name, d.signed_pdf) for d in result.docs if d.signed_pdf is not None]

    body = ""
    if result.docs:
        from app.processor import build_email_body
        body = build_email_body(result.subject, result.docs)

    mailbox.append_to_folder(folder=dest, subject=result.subject,
                             sender=result.sender, body=body, signed_pdfs=signed_pdfs)

    mailbox.move_to_archive(uid)

    if dest == cfg["folder_yellow"]:
        queue_item = {
            "uid": uid,
            "subject": result.subject,
            "sender": result.sender,
            "received_at": _now(),
            "pdf_count": len(result.docs),
            "documents": [
                {"name": d.name, "template": d.template, "score": d.score,
                 "light": d.light, "anchor_count": d.anchor_count,
                 "anchors": d.anchors, "error": d.error}
                for d in result.docs
            ],
        }
        queue_index.add_item(queue_item)

    log_entry = {
        "ts": _now(), "uid": uid, "subject": result.subject, "sender": result.sender,
        "pdfs": [{"name": d.name, "template": d.template, "score": d.score,
                  "light": d.light, "anchors": d.anchor_count, "error": d.error}
                 for d in result.docs],
        "destination": dest, "reply_sent": False, "error": result.error,
    }
    activity_log.append_log(log_entry)
    logger.info("uid=%s routed → %s", uid, dest)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
