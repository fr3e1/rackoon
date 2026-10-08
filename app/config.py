"""Single-file JSON config: servers, scripts, settings and auth.

Everything needed to move the manager to another machine lives in
DATA_DIR/config.json, so copying that file (or using Export/Import in the UI)
is enough.
"""

import json
import os
import secrets
import shutil
import threading
import uuid
from pathlib import Path

# User data lives outside the project folder so it can never be committed.
# RACKOON_DATA_DIR overrides it (the Docker image uses /data).
PROJECT_DIR = Path(__file__).resolve().parent.parent
_XDG_DATA = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
DATA_DIR = Path(os.environ.get("RACKOON_DATA_DIR") or _XDG_DATA / "rackoon").expanduser()
CONFIG_PATH = DATA_DIR / "config.json"
# Where older versions kept their data, newest first.
LEGACY_DATA_DIRS = [_XDG_DATA / "server-manager", PROJECT_DIR / "data"]

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


def ensure_data_dir() -> None:
    """Create the data dir (owner-only) and, on the first start with it, move
    data over from a location an older version used."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(DATA_DIR, 0o700)
    if CONFIG_PATH.exists():
        return
    for legacy in LEGACY_DATA_DIRS:
        if not (legacy / "config.json").exists() or legacy.resolve() == DATA_DIR.resolve():
            continue
        for item in legacy.iterdir():
            shutil.move(str(item), DATA_DIR / item.name)
        legacy.rmdir()
        print(f"Moved user data from {legacy} to {DATA_DIR}")
        return


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
