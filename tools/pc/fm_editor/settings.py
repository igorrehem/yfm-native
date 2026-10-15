"""The editor's own settings (View > Dark mode), in a small JSON file of its
own: %APPDATA%/FM Editor/settings.json on Windows, else fm-editor/settings.json
under an absolute XDG_CONFIG_HOME or ~/.config. Not the port's user directory:
that is the game's. A missing or unreadable file is no settings."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def path() -> Path:
    appdata = os.environ.get("APPDATA")
    if sys.platform == "win32" and appdata:
        return Path(appdata) / "FM Editor" / "settings.json"
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    base = xdg if xdg.startswith("/") else os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "fm-editor" / "settings.json"


def load() -> dict:
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(key: str, value) -> str | None:
    """Store one setting beside the others; the problem, or None."""
    data = load()
    data[key] = value
    target = path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    except OSError as problem:
        return str(problem)
    return None
