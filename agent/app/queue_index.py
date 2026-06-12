"""Управление review_queue.json — единственный писатель: agent."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from app.config import ORIGINALS_DIR, QUEUE_FILE, SIGNED_DIR

logger = logging.getLogger(__name__)


def _ensure_dirs() -> None:
    os.makedirs(os.path.dirname(QUEUE_FILE), exist_ok=True)


def load_queue() -> dict:
    _ensure_dirs()
    try:
        with open(QUEUE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"updated_at": _now(), "items": []}
    except Exception as e:
        logger.error("load_queue: %s", e)
        return {"updated_at": _now(), "items": []}


def _save_queue(queue: dict) -> None:
    _ensure_dirs()
    queue["updated_at"] = _now()
    tmp = QUEUE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
    os.replace(tmp, QUEUE_FILE)


def add_item(item: dict) -> None:
    queue = load_queue()
    queue["items"] = [i for i in queue["items"] if i.get("uid") != item.get("uid")]
    queue["items"].append(item)
    _save_queue(queue)
    logger.info("queue: added uid=%s", item.get("uid"))


def remove_item(uid: str) -> bool:
    queue = load_queue()
    before = len(queue["items"])
    queue["items"] = [i for i in queue["items"] if i.get("uid") != uid]
    removed = len(queue["items"]) < before
    if removed:
        _save_queue(queue)
        logger.info("queue: removed uid=%s", uid)
    return removed


def get_item(uid: str) -> dict | None:
    queue = load_queue()
    return next((i for i in queue["items"] if i.get("uid") == uid), None)


def get_signed_pdfs(uid: str) -> list[dict]:
    import base64
    uid_dir = os.path.join(SIGNED_DIR, uid)
    if not os.path.isdir(uid_dir):
        return []
    result = []
    for fname in sorted(os.listdir(uid_dir)):
        if fname.lower().endswith(".pdf"):
            try:
                with open(os.path.join(uid_dir, fname), "rb") as f:
                    result.append({"name": fname, "b64": base64.b64encode(f.read()).decode()})
            except Exception as e:
                logger.error("get_signed_pdfs uid=%s fname=%s: %s", uid, fname, e)
    return result


def get_original_pdfs(uid: str) -> list[dict]:
    """Оригинальные (неподписанные) PDF письма — для переподписания оператором."""
    import base64
    uid_dir = os.path.join(ORIGINALS_DIR, uid)
    if not os.path.isdir(uid_dir):
        return []
    result = []
    for fname in sorted(os.listdir(uid_dir)):
        if fname.lower().endswith(".pdf"):
            try:
                with open(os.path.join(uid_dir, fname), "rb") as f:
                    result.append({"name": fname, "b64": base64.b64encode(f.read()).decode()})
            except Exception as e:
                logger.error("get_original_pdfs uid=%s fname=%s: %s", uid, fname, e)
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
