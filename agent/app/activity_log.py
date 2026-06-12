"""Журнал активности агента — agent_log.jsonl."""
from __future__ import annotations

import json
import logging
import os
from typing import Callable

from app.config import LOG_FILE, LOG_MAX_ENTRIES

logger = logging.getLogger(__name__)


def _ensure_dirs() -> None:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


def append_log(entry: dict) -> None:
    _ensure_dirs()
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _rotate_if_needed()
    except Exception as e:
        logger.error("append_log: %s", e)


def read_last_n(n: int = 50, filter_fn: Callable | None = None) -> list[dict]:
    _ensure_dirs()
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []

    entries = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if filter_fn is None or filter_fn(entry):
                entries.append(entry)
            if len(entries) >= n:
                break
        except Exception:
            continue
    return list(reversed(entries))


def _rotate_if_needed() -> None:
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) <= LOG_MAX_ENTRIES:
            return
        trimmed = lines[-LOG_MAX_ENTRIES:]
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.writelines(trimmed)
    except Exception as e:
        logger.error("_rotate_if_needed: %s", e)
