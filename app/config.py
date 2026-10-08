"""Single-file JSON config: servers, scripts, settings and auth.

Everything needed to move the manager to another machine lives in
DATA_DIR/config.json, so copying that file (or using Export/Import in the UI)
is enough.
"""

import json
import os
import secrets
import threading
import uuid
from pathlib import Path

DATA_DIR = Path(os.environ.get("SM_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
CONFIG_PATH = DATA_DIR / "config.json"

DEFAULT_SETTINGS = {
    "status_interval": 30,  # seconds between online checks
    "ssh_timeout": 10,  # seconds to wait for an SSH connection
}

_lock = threading.Lock()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def _default() -> dict:
    return {
        "version": 1,
        "auth": {"password_hash": None, "secret": secrets.token_hex(32)},
        "settings": dict(DEFAULT_SETTINGS),
        "servers": [],
        "scripts": [],
    }


def load() -> dict:
    with _lock:
        if not CONFIG_PATH.exists():
            cfg = _default()
            _write(cfg)
            return cfg
        cfg = json.loads(CONFIG_PATH.read_text())
    cfg.setdefault("auth", {}).setdefault("secret", secrets.token_hex(32))
    cfg["auth"].setdefault("password_hash", None)
    cfg["settings"] = {**DEFAULT_SETTINGS, **cfg.get("settings", {})}
    cfg.setdefault("servers", [])
    cfg.setdefault("scripts", [])
    return cfg


def save(cfg: dict) -> None:
    with _lock:
        _write(cfg)


def _write(cfg: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2))
    os.chmod(tmp, 0o600)  # contains SSH credentials
    tmp.replace(CONFIG_PATH)
