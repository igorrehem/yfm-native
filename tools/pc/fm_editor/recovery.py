"""Separate JSON recovery copies and rotating backups of saved mod folders.

A copy hard-links each file unchanged since the previous copy (same size and
time, and settled before that copy was made) instead of copying it again, so
a large mod's art costs its disk space once and an autosave takes no time.
Copies are never written into after they are made, so sharing is safe.

The editor takes what a copy needs from the project on its own thread
(Recovery.prepare: the undo history's snapshot, a few names) and writes it
on another (Writer), so a big mod's copy does not stop the window."""
from __future__ import annotations

import gc
import hashlib
import itertools
import json
import os
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import manifest, settings
from .history import Snapshot


def root():
    return settings.path().parent / "recovery"


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SETTLE_SECONDS = 2      # a file this close to the previous copy's time is copied again


def _unchanged(item, old, settled):
    try:
        a, b = item.stat(), old.stat()
    except OSError:
        return False
    return (a.st_size == b.st_size and a.st_mtime_ns == b.st_mtime_ns
            and a.st_mtime < settled - SETTLE_SECONDS)


def fill(source, destination, previous=None, settled=0.0, skip=lambda rel: False, followlinks=False):
    """Copy the files of `source` that `destination` does not have yet. One
    unchanged since the copy in `previous` (made at `settled`) is linked to
    it; a file system without hard links gets a plain copy."""
    source, destination = Path(source), Path(destination)
    for directory, subdirs, files in os.walk(source, followlinks=followlinks):
        directory = Path(directory)
        subdirs[:] = [name for name in subdirs if (directory / name).resolve() != destination.resolve()]
        for name in files:
            item = directory / name
            rel = item.relative_to(source)
            target = destination / rel
            if skip(rel) or not item.is_file() or os.path.lexists(target):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if previous is not None and _unchanged(item, Path(previous) / rel, settled):
                try:
                    os.link(Path(previous) / rel, target)
                    continue
                except OSError:
                    pass
            shutil.copy2(item, target)


@dataclass
class Job:
    """Everything a copy reads from the live project, taken beforehand: the
    write needs nothing else of it and can run on another thread."""
    snapshot: Snapshot
    retail: object
    source: object                  # the mod folder it was read from, or None
    owned: set = field(default_factory=set)     # roster.owned's files of that folder
    name: str = ""
    forms: dict = field(default_factory=dict)


class Recovery:
    def __init__(self):
        self.folder = root() / ("session-" + uuid.uuid4().hex)

    def prepare(self, project, forms=None, snapshot=None) -> Job:
        """On the editor's thread. snapshot: the project's state already
        taken (the history's current one), so a big mod is not pickled twice."""
        if project.source_dir and self.folder.resolve().is_relative_to(Path(project.source_dir).resolve()):
            raise ValueError("The recovery folder is inside this mod; choose a different mod folder.")
        return Job(snapshot or Snapshot(project), project.retail, project.source_dir,
                   set(getattr(project, "roster_owned", ()) or ()), project.info.name,
                   json.loads(json.dumps(forms or {})))

    def write(self, project, forms=None, snapshot=None):
        return self.write_job(self.prepare(project, forms, snapshot))

    def write_job(self, job: Job):
        """The copy itself: on any thread, one at a time for this folder."""
        self.folder.mkdir(parents=True, exist_ok=True)
        generation = self.folder / uuid.uuid4().hex
        previous = None
        settled = 0.0
        index = self.folder / "recovery.json"
        if index.exists():
            settled = index.stat().st_mtime
            saved = json.loads(index.read_text(encoding="utf-8"))
            previous = saved.get("generation") if isinstance(saved, dict) else None
            if not isinstance(previous, str) or len(previous) != 32 or any(c not in "0123456789abcdef" for c in previous):
                raise ValueError("The previous recovery index is invalid; its files were left untouched.")
        try:
            clone = job.snapshot.restore(job.retail, job.source)
            manifest.save_mod(clone, generation, copy_source=False)
            source = job.source
            if source and Path(source).is_dir():
                # What save_mod would copy first; the files it wrote win.
                # The roster's files it read are its own to write (roster.py):
                # a duelist taken out must not come back with its file.
                fill(source, generation, self.folder / previous if previous else None, settled,
                     skip=lambda rel: rel.name == "mod.json" or rel.as_posix() in job.owned)
            record = {"name": job.name, "time": stamp(), "generation": generation.name,
                      "source": str(job.source or ""), "forms": job.forms}
            temporary = index.with_suffix(".tmp")
            temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(index)
        except Exception:
            shutil.rmtree(generation, ignore_errors=True)
            raise
        if previous:
            shutil.rmtree(self.folder / previous, ignore_errors=True)
        return index

    def clear(self):
        shutil.rmtree(self.folder, ignore_errors=True)


# Python's cycle collector runs on whichever thread allocates when it is due.
# On the writer's thread it would finalize the Tk objects garbage holds (a
# closed dialog's variables and images, a destroyed window): tkinter then
# calls Tcl from the wrong thread, which outside mainloop waits a second and
# fails, inside it queues the call to the window's thread (stuck while that
# thread waits for the copy), and for a whole interpreter aborts the process
# ("Tcl_AsyncDelete: async handler deleted by the wrong thread"). So while a
# copy is written the collector waits, and the window's thread turns it back
# on once the writer has finished.
_gc_lock = threading.Lock()
_gc_writers = 0
_gc_was_enabled = False


def _pause_gc():
    global _gc_writers, _gc_was_enabled
    with _gc_lock:
        if _gc_writers == 0:
            _gc_was_enabled = gc.isenabled()
            gc.disable()
        _gc_writers += 1


def _resume_gc():
    global _gc_writers
    with _gc_lock:
        _gc_writers -= 1
        if _gc_writers == 0 and _gc_was_enabled:
            gc.enable()


class Writer:
    """One copy written on a thread of its own. The window asks done() from
    its own thread (Tk is never called from this one); cancel() (the mod was
    saved or closed meanwhile) has the copy removed once it is written. The
    cycle collector waits while it runs (_pause_gc): done() or wait(), on the
    window's thread, turn it back on."""

    def __init__(self, recovery: Recovery, job: Job):
        self.recovery, self.job = recovery, job
        self.error = None
        self._lock = threading.Lock()
        self._cancelled = False
        self._gc_paused = False
        self._thread = threading.Thread(target=self._run, name="FM Editor recovery copy")

    def start(self):
        _pause_gc()
        self._gc_paused = True
        try:
            self._thread.start()
        except BaseException:
            self._finished()
            raise
        return self

    def _finished(self):
        if self._gc_paused:
            self._gc_paused = False
            _resume_gc()

    def _run(self):
        try:
            self.recovery.write_job(self.job)
        except Exception as problem:        # reported by the window, on its thread
            self.error = problem
        with self._lock:
            if self._cancelled:
                self.recovery.clear()

    def cancel(self):
        with self._lock:
            self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def done(self) -> bool:
        if self._thread.is_alive():
            return False
        self._finished()
        return True

    def wait(self):
        self._thread.join()
        self._finished()


def backup(folder, keep=5):
    """Copy the previous mod and all assets before any existing file is replaced."""
    folder = Path(folder).resolve()
    if not (folder / "mod.json").is_file():
        return None
    if manifest.is_game_folder(folder):
        raise ValueError(f"{folder} holds game files; the editor writes mod folders only")
    group = root() / "backups" / hashlib.sha256(str(folder).encode()).hexdigest()[:16]
    # A recovery store placed inside a mod must never copy itself recursively.
    if group.resolve().is_relative_to(folder):
        raise ValueError("The recovery folder is inside this mod; choose a different save folder.")
    destination = group / uuid.uuid4().hex
    last = max(group.glob("*/recovery.json"), key=lambda p: p.stat().st_mtime_ns, default=None)
    try:
        (destination / "mod").mkdir(parents=True)
        fill(folder, destination / "mod", last.parent / "mod" if last else None,
             last.stat().st_mtime if last else 0.0, followlinks=True)
        (destination / "recovery.json").write_text(json.dumps({
            "name": folder.name, "time": stamp(), "source": str(folder), "generation": "mod",
            "backup": True}), encoding="utf-8")
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    old = sorted(group.glob("*/recovery.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
    for index in old[keep:]:
        shutil.rmtree(index.parent, ignore_errors=True)
    return destination


def records(exclude=None):
    found = []
    indexes = itertools.chain(root().glob("session-*/recovery.json"), root().glob("backups/*/*/recovery.json"))
    for index in indexes:
        if exclude is not None and index.parent == exclude:
            continue
        try:
            data = json.loads(index.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("time", ""), str):
                continue
            generation = data["generation"]
            if not isinstance(generation, str) or Path(generation).name != generation or generation in (".", ".."):
                continue
            folder = index.parent / generation
            if (folder / "mod.json").is_file():
                found.append((index, folder, data))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(found, key=lambda row: row[2].get("time", ""), reverse=True)
