"""Mailbox — обёртка над ImapSource. Единственный, кто двигает IMAP-письма."""
from __future__ import annotations

import logging
from app.config import load_mail_config

logger = logging.getLogger(__name__)

_source = None
_source_key = None
_sink = None
_sink_key = None


def _get_source():
    global _source, _source_key
    cfg = load_mail_config()
    if not cfg["imap_host"]:
        raise RuntimeError("IMAP не настроен (mail_config.json пуст и env пуст)")
    key = (cfg["imap_host"], cfg["imap_port"], cfg["imap_user"], cfg["folder_in"],
           cfg.get("auth_method", "basic"))
    if _source is None or _source_key != key:
        from signfinder.intake.imap_source import ImapSource
        _source = ImapSource(
            host=cfg["imap_host"], port=cfg["imap_port"], user=cfg["imap_user"],
            password=cfg["imap_password"], ssl=cfg["imap_ssl"], folder_in=cfg["folder_in"],
            auth_method=cfg.get("auth_method", "basic"),
            oauth2_provider=cfg.get("oauth2_provider", ""),
            oauth2_client_id=cfg.get("oauth2_client_id", ""),
            oauth2_client_secret=cfg.get("oauth2_client_secret", ""),
            oauth2_refresh_token=cfg.get("oauth2_refresh_token", ""),
            oauth2_token_endpoint=cfg.get("oauth2_token_endpoint", ""),
        )
        _source_key = key
    return _source


def _get_sink():
    global _sink, _sink_key
    cfg = load_mail_config()
    if not cfg["smtp_host"]:
        return None
    key = (cfg["smtp_host"], cfg["smtp_port"], cfg["smtp_user"],
           cfg.get("auth_method", "basic"))
    if _sink is None or _sink_key != key:
        from signfinder.intake.smtp_sink import SmtpSink
        _sink = SmtpSink(
            host=cfg["smtp_host"], port=cfg["smtp_port"],
            user=cfg["smtp_user"], password=cfg["smtp_password"],
            auth_method=cfg.get("auth_method", "basic"),
            oauth2_provider=cfg.get("oauth2_provider", ""),
            oauth2_client_id=cfg.get("oauth2_client_id", ""),
            oauth2_client_secret=cfg.get("oauth2_client_secret", ""),
            oauth2_refresh_token=cfg.get("oauth2_refresh_token", ""),
            oauth2_token_endpoint=cfg.get("oauth2_token_endpoint", ""),
        )
        _sink_key = key
    return _sink


def ensure_all_folders() -> None:
    """Создаёт все 5 IMAP-папок из конфига до первой обработки. Идемпотентно."""
    cfg = load_mail_config()
    src = _get_source()
    src._connect()
    for key in ("folder_in", "folder_green", "folder_yellow", "folder_red", "folder_archive"):
        try:
            src._ensure_folder(cfg[key])
        except Exception as e:
            logger.warning("ensure_all_folders: %s (%s) failed: %s", key, cfg[key], e)


def poll_inbox() -> list:
    return _get_source().poll()


def append_to_folder(folder: str, subject: str, sender: str,
                     body: str, signed_pdfs: list[tuple[str, bytes]]) -> None:
    cfg = load_mail_config()
    from signfinder.intake.smtp_sink import build_processed_email
    raw = build_processed_email(
        original_subject=subject, original_sender=sender,
        body_text=body, signed_pdfs=signed_pdfs,
    )
    _get_source().append(folder, raw)

    if cfg["reply_to_sender"] and _get_sink() and sender:
        try:
            from signfinder.intake.base import IntakeAttachment
            _get_sink().deliver(
                to_addr=sender,
                subject=f"[SignFinder] {subject}",
                body=body,
                attachments=[
                    IntakeAttachment(filename=fn, content=pb, content_type="application/pdf")
                    for fn, pb in signed_pdfs
                ],
            )
        except Exception as e:
            logger.error("reply_to_sender failed: %s", e)


def move_to_archive(uid: str) -> None:
    cfg = load_mail_config()
    _get_source().move(uid, cfg["folder_archive"], source_folder=cfg["folder_in"])


def move_yellow_to(uid: str, dest: str) -> None:
    cfg = load_mail_config()
    _get_source().move(uid, dest, source_folder=cfg["folder_yellow"])


def do_resolve(uid: str, action: str, new_anchors: list | None = None) -> dict:
    from app.queue_index import get_item, remove_item
    from app.activity_log import append_log
    from datetime import datetime, timezone

    cfg = load_mail_config()
    item = get_item(uid)
    if not item:
        raise ValueError(f"UID {uid} не найден в очереди")

    subject = item.get("subject", "")
    sender = item.get("sender", "")

    def _now():
        return datetime.now(timezone.utc).isoformat()

    if action == "confirm":
        move_yellow_to(uid, cfg["folder_green"])
        remove_item(uid)
        append_log({"ts": _now(), "uid": uid, "action": "confirm", "subject": subject, "dest": cfg["folder_green"]})
        return {"status": "ok", "action": "confirm", "dest": cfg["folder_green"]}

    elif action == "resign":
        from app.processor import resign_item, build_email_body, DocResult
        try:
            signed = resign_item(uid, item, new_anchors)
        except Exception as e:
            raise RuntimeError(f"resign failed: {e}")

        docs_meta = item.get("documents", [])
        doc_results = [
            DocResult(name=d.get("name", ""), original_name=d.get("name", ""),
                      light="green", template=d.get("template", ""),
                      score=d.get("score"), anchor_count=d.get("anchor_count", 0))
            for d in docs_meta
        ]
        body = build_email_body(subject, doc_results)
        append_to_folder(cfg["folder_green"], subject, sender, body, signed)
        move_yellow_to(uid, cfg["folder_archive"])
        remove_item(uid)
        append_log({"ts": _now(), "uid": uid, "action": "resign", "subject": subject, "dest": cfg["folder_green"]})
        return {"status": "ok", "action": "resign", "dest": cfg["folder_green"]}

    elif action == "reject":
        move_yellow_to(uid, cfg["folder_red"])
        remove_item(uid)
        append_log({"ts": _now(), "uid": uid, "action": "reject", "subject": subject, "dest": cfg["folder_red"]})
        return {"status": "ok", "action": "reject", "dest": cfg["folder_red"]}

    raise ValueError(f"Unknown action: {action}")
