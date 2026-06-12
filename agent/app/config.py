"""signfinder-agent — конфигурация из env vars."""
from __future__ import annotations
import json
import os

# API
SIGNFINDER_API_URL: str = os.environ.get("SIGNFINDER_API_URL", "http://api:8000")
SIGNFINDER_API_KEY: str = os.environ.get("SIGNFINDER_API_KEY", "")
SIGNER_ID: str = os.environ.get("SIGNER_ID", "default")

# IMAP (module-level константы — для обратной совместимости, не использовать в mailbox/poller)
IMAP_HOST: str = os.environ.get("IMAP_HOST", "")
IMAP_PORT: int = int(os.environ.get("IMAP_PORT", "993"))
IMAP_USER: str = os.environ.get("IMAP_USER", "")
IMAP_PASSWORD: str = os.environ.get("IMAP_PASSWORD", "")
IMAP_SSL: bool = os.environ.get("IMAP_SSL", "true").lower() == "true"

# SMTP (опционально)
SMTP_HOST: str = os.environ.get("SMTP_HOST", "")
SMTP_PORT: int = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER: str = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD: str = os.environ.get("SMTP_PASSWORD", "")

# Папки IMAP
FOLDER_IN: str = os.environ.get("FOLDER_IN", "SignfinderIn")
FOLDER_GREEN: str = os.environ.get("FOLDER_GREEN", "SignfinderGreen")
FOLDER_YELLOW: str = os.environ.get("FOLDER_YELLOW", "SignfinderYellow")
FOLDER_RED: str = os.environ.get("FOLDER_RED", "SignfinderRed")
FOLDER_ARCHIVE: str = os.environ.get("FOLDER_ARCHIVE", "SignfinderArchive")

# Поведение
POLL_INTERVAL_SEC: int = int(os.environ.get("POLL_INTERVAL_SEC", "300"))
REPLY_TO_SENDER: bool = os.environ.get("REPLY_TO_SENDER", "false").lower() == "true"
LOG_MAX_ENTRIES: int = int(os.environ.get("LOG_MAX_ENTRIES", "1000"))

# Хранилище
DATA_PATH: str = os.environ.get("DATA_PATH", "/data")
AGENT_DATA_DIR: str = os.path.join(DATA_PATH, "agent")
QUEUE_FILE: str = os.path.join(AGENT_DATA_DIR, "review_queue.json")
LOG_FILE: str = os.path.join(AGENT_DATA_DIR, "agent_log.jsonl")
ORIGINALS_DIR: str = os.path.join(AGENT_DATA_DIR, "pdfs", "originals")
SIGNED_DIR: str = os.path.join(AGENT_DATA_DIR, "pdfs", "signed")

MAIL_CONFIG_PATH = os.path.join(DATA_PATH, "settings", "mail_config.json")


def load_mail_config() -> dict:
    """Читает mail_config.json (приоритет) с fallback на env vars.
    Читается при каждом вызове — подхватывает изменения из UI без рестарта.
    """
    cfg: dict = {}
    try:
        with open(MAIL_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cfg = {}

    def _get(json_key, env_key, default):
        val = cfg.get(json_key)
        if val not in (None, ""):
            return val
        return os.environ.get(env_key, default)

    raw_ssl = _get("imap_ssl", "IMAP_SSL", "true")
    if isinstance(raw_ssl, bool):
        imap_ssl = raw_ssl
    else:
        imap_ssl = str(raw_ssl).lower() in ("true", "1", "yes")

    raw_reply = _get("reply_to_sender", "REPLY_TO_SENDER", "false")
    if isinstance(raw_reply, bool):
        reply_to_sender = raw_reply
    else:
        reply_to_sender = str(raw_reply).lower() in ("true", "1", "yes")

    return {
        "imap_host": _get("imap_host", "IMAP_HOST", ""),
        "imap_port": int(_get("imap_port", "IMAP_PORT", 993)),
        "imap_user": _get("imap_user", "IMAP_USER", ""),
        "imap_password": _get("imap_password", "IMAP_PASSWORD", ""),
        "imap_ssl": imap_ssl,
        "smtp_host": _get("smtp_host", "SMTP_HOST", ""),
        "smtp_port": int(_get("smtp_port", "SMTP_PORT", 587)),
        "smtp_user": _get("smtp_user", "SMTP_USER", ""),
        "smtp_password": _get("smtp_password", "SMTP_PASSWORD", ""),
        "folder_in": _get("folder_in", "FOLDER_IN", "SignfinderIn"),
        "folder_green": _get("folder_green", "FOLDER_GREEN", "SignfinderGreen"),
        "folder_yellow": _get("folder_yellow", "FOLDER_YELLOW", "SignfinderYellow"),
        "folder_red": _get("folder_red", "FOLDER_RED", "SignfinderRed"),
        "folder_archive": _get("folder_archive", "FOLDER_ARCHIVE", "SignfinderArchive"),
        "poll_interval_sec": int(_get("poll_interval_sec", "POLL_INTERVAL_SEC", 300)),
        "reply_to_sender": reply_to_sender,
        "auth_method": _get("auth_method", "AUTH_METHOD", "basic"),
        "oauth2_provider": _get("oauth2_provider", "OAUTH2_PROVIDER", ""),
        "oauth2_client_id": _get("oauth2_client_id", "OAUTH2_CLIENT_ID", ""),
        "oauth2_client_secret": _get("oauth2_client_secret", "OAUTH2_CLIENT_SECRET", ""),
        "oauth2_refresh_token": _get("oauth2_refresh_token", "OAUTH2_REFRESH_TOKEN", ""),
        "oauth2_token_endpoint": _get("oauth2_token_endpoint", "OAUTH2_TOKEN_ENDPOINT", ""),
    }
