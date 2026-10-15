#!/usr/bin/env python3
"""Extract and run an FM Editor release archive on the host platform.

Uses synthetic game data in the executable's self-test, never a retail ROM.
Linux needs a display: xvfb-run -a python tools/pc/test_editor_package.py ARCHIVE
"""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile
import zipfile

TABS = ["Cards", "Art", "Fusions", "Equips", "Rituals", "Duelists", "UI", "Starter decks", "Map",
        "Values", "Guardian Stars", "Packs", "Tower", "Mod info", "Conflicts"]


def require(condition, message):
    """A failed check, even under python -O (where assert is skipped)."""
    if not condition:
        raise SystemExit(f"editor package check failed: {message}")


def check(archive: Path, version=None, commit=None):
    # ignore_cleanup_errors: Windows may still hold the just-exited editor's files.
    with tempfile.TemporaryDirectory(prefix="fm-editor-package-", ignore_cleanup_errors=True) as temporary:
        folder = Path(temporary) / "Editor space-é"
        folder.mkdir()
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as package:
                require(package.testzip() is None, "corrupt ZIP")
                names = package.namelist()
                validate_names(names)
                package.extractall(folder)
            program = "fm-editor.exe"
        else:
            with tarfile.open(archive) as package:
                members = package.getmembers()
                require(all(m.isfile() or m.isdir() for m in members), "unexpected archive member")
                names = package.getnames()
                validate_names(names)
                package.extractall(folder, filter="data")
            program = "fm-editor"
        roots = {PurePosixPath(name).parts[0] for name in names}
        require(len(roots) == 1, "expected one release folder")
        root = folder / roots.pop()
        executable = root / program
        require(executable.is_file(), "missing editor executable")
        require((root / "fm-editor-README.md").is_file(), "missing guide")
        if program.endswith(".exe"):
            require((root / "fm-editor.pkg").is_file(), "missing Python archive")
            require((root / "fm-editor-files").is_dir(), "missing editor dependencies")
        else:
            require(os.access(executable, os.X_OK), "editor is not executable")
        report_path = folder / "result.json"
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
        env.update(XDG_CONFIG_HOME=str(folder / "config"), APPDATA=str(folder / "config"))
        result = subprocess.run([str(executable), "self-test", "--output", str(report_path)],
                                cwd=folder, env=env, capture_output=True, text=True, timeout=180)
        require(report_path.is_file(),
                f"editor wrote no report (exit {result.returncode}): {result.stderr}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        require(result.returncode == 0 and report.get("ok"), report)
        require(report.get("tabs") == TABS, f"tabs {report.get('tabs')}, expected {TABS}")
        require(set(report["ui_pages"]) == {"title", "menu", "duel", "board"}, report)
        if version:
            require(report["build"]["version"] == version, report)
        if commit:
            require(report["build"]["commit"] == commit, report)
        print(json.dumps(report, indent=2))


def validate_names(names):
    for name in names:
        path = PurePosixPath(name)
        require(path.parts and not path.is_absolute() and ".." not in path.parts,
                f"unexpected archive path: {name}")
        require(":" not in name and "\\" not in name, f"unexpected archive path: {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--version")
    parser.add_argument("--commit", default=os.environ.get("GITHUB_SHA"))
    args = parser.parse_args()
    check(args.archive.resolve(), args.version, args.commit)
