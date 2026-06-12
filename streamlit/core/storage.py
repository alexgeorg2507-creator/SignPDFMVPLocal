"""Config storage — local filesystem mode only.

LocalDocker variant: GCS_BUCKET not set → always uses config/ directory.
"""
import json
import os
from datetime import datetime
from pathlib import Path

LOCAL_CONFIG_DIR = Path(__file__).parent.parent / "config"


def _ensure_dir():
    LOCAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def read_md(filename: str) -> str:
    _ensure_dir()
    p = LOCAL_CONFIG_DIR / filename
    return p.read_text(encoding="utf-8") if p.exists() else ""


def write_md(filename: str, content: str) -> str:
    _ensure_dir()
    backup_name = _backup_name(filename, "md")
    path = LOCAL_CONFIG_DIR / filename
    _local_backup(path, backup_name)
    path.write_text(content, encoding="utf-8")
    return backup_name


def read_json(filename: str) -> dict:
    _ensure_dir()
    return json.loads((LOCAL_CONFIG_DIR / filename).read_text(encoding="utf-8"))


def write_json(filename: str, data: dict) -> str:
    _ensure_dir()
    backup_name = _backup_name(filename, "json")
    content = json.dumps(data, ensure_ascii=False, indent=2)
    path = LOCAL_CONFIG_DIR / filename
    _local_backup(path, backup_name)
    path.write_text(content, encoding="utf-8")
    return backup_name


def read_signature() -> bytes | None:
    try:
        path = LOCAL_CONFIG_DIR / "signature.png"
        return path.read_bytes() if path.exists() else None
    except Exception:
        return None


def write_signature(png_bytes: bytes) -> None:
    _ensure_dir()
    (LOCAL_CONFIG_DIR / "signature.png").write_bytes(png_bytes)


def json_config_exists(filename: str = "parties.json") -> bool:
    return (LOCAL_CONFIG_DIR / filename).exists()


def _backup_name(filename: str, ext: str) -> str:
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = Path(filename).stem
    return f"{stem}_{ts}.{ext}"


def _local_backup(path: Path, backup_name: str) -> None:
    if path.exists():
        backup_dir = LOCAL_CONFIG_DIR / "backups"
        backup_dir.mkdir(exist_ok=True)
        (backup_dir / backup_name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
