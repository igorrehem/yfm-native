"""Build identity shared by About, --version and packaged smoke checks."""
from __future__ import annotations

import functools
import json
from pathlib import Path
import subprocess
import sys
import threading

from .compat import HOST_API


def source_info(version="", commit=None) -> dict:
    # Release CI supplies its checkout SHA, including inside the Linux
    # build container where Git may not be installed or trust the mount.
    if commit:
        return {"version": version or "development", "commit": commit, "mod_api": HOST_API}
    root = Path(__file__).resolve().parents[3]
    commit = "unknown"
    try:
        commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                         stderr=subprocess.DEVNULL, text=True, timeout=5).strip()
        dirty = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"],
                                        stderr=subprocess.DEVNULL, text=True, timeout=5)
        if dirty.strip():
            commit += " (modified)"
    except (OSError, subprocess.SubprocessError):
        pass
    return {"version": version or "development", "commit": commit, "mod_api": HOST_API}


@functools.lru_cache(maxsize=None)
def _current() -> dict:
    if getattr(sys, "frozen", False):
        return json.loads(Path(__file__).with_name("build-info.json").read_text(encoding="utf-8"))
    return source_info()


_lock = threading.Lock()


def current() -> dict:
    """The build's identity, worked out once a run: from source that is two
    git commands, which About must not wait on each time (prefetch())."""
    with _lock:
        return _current()


def prefetch():
    """Work out current() off the Tk thread, so About shows it at once."""
    threading.Thread(target=current, name="build-info", daemon=True).start()


def description() -> str:
    info = current()
    return f"FM Editor {info['version']}\nCommit: {info['commit']}\nMod API: {info['mod_api']}"
