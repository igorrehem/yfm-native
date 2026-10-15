#!/usr/bin/env python3
"""Build the editor as a program of its own with PyInstaller.

    python -m pip install pyinstaller
    python tools/pc/fm_editor/build_exe.py [--dist tmp/pc/fm-editor] [--version v0.1.3]

Writes <dist>/fm-editor, a program that needs no Python on the player's
machine. On Windows that is fm-editor.exe, fm-editor.pkg and
fm-editor-files/, which stay together; elsewhere one file. The build files stay under <dist>; nothing it writes
belongs in git.

Windows gets no one-file build: that is a small loader with the whole
program appended, unpacked to a temporary folder on every start, which is
what droppers look like to virus scanners (Defender flagged it as
Trojan:Win32/Wacatac.B!ml). The folder build carries version information
too, which scanners also like to see.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def version_info(label: str) -> str:
    """A PyInstaller version file for fm-editor.exe."""
    match = re.match(r"v(\d+)\.(\d+)\.(\d+)", label)
    numbers = tuple(int(n) for n in match.groups()) + (0,) if match else (0, 0, 0, 0)
    text = label or "development build"
    strings = {"CompanyName": "Yu-Gi-Oh! Forbidden Memories Recompiled",
               "FileDescription": "FM Editor (Yu-Gi-Oh! Forbidden Memories Recompiled mod editor)",
               "FileVersion": text, "InternalName": "fm-editor", "OriginalFilename": "fm-editor.exe",
               "ProductName": "Yu-Gi-Oh! Forbidden Memories Recompiled", "ProductVersion": text,
               "Comments": "https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled"}
    entries = ",\n".join(f"          StringStruct({key!r}, {value!r})" for key, value in strings.items())
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
{entries}])]),
    VarFileInfo([VarStruct('Translation', [0x0409, 1200])])
  ]
)
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dist", type=Path, default=ROOT / "tmp" / "pc" / "fm-editor")
    parser.add_argument("--console", action="store_true", help="keep a console window (for the command line)")
    parser.add_argument("--version", default="", help="the release, vX.Y.Z[-PRE], for the version information")
    parser.add_argument("--commit", default=os.environ.get("GITHUB_SHA"), help="source commit (default: Git checkout)")
    arguments = parser.parse_args()
    dist = arguments.dist.resolve()
    work = dist / "build"
    work.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(HERE.parent))
    from fm_editor.build_info import source_info
    identity = work / "build-info.json"
    identity.write_text(json.dumps(source_info(arguments.version, arguments.commit)), encoding="utf-8")
    build = ["--noconfirm", "--clean", "--distpath", str(dist), "--workpath", str(work)]
    program = ["--name", "fm-editor", "--specpath", str(work), "--paths", str(HERE.parent),
               "--hidden-import", "text_listing", "--collect-submodules", "fm_editor",
               "--add-data", f"{identity}{os.pathsep}fm_editor"]
    if sys.platform == "win32":
        version_file = work / "version.txt"
        version_file.write_text(version_info(arguments.version), encoding="utf-8")
        program += ["--onedir", "--contents-directory", "fm-editor-files", "--version-file", str(version_file)]
    else:
        program.append("--onefile")
    if not arguments.console:
        program.append("--windowed")
    program.append(str(HERE / "__main__.py"))
    # The spec's collect_submodules imports fm_editor before --paths is in
    # effect; without this it finds nothing and the pages the UI tab loads
    # by name (ui_title, ui_duel, ui_board) are left out of the program.
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(HERE.parent), env.get("PYTHONPATH")]))
    makespec = [sys.executable, "-m", "PyInstaller.utils.cliutils.makespec", *program]
    print(" ".join(makespec))
    if subprocess.run(makespec, cwd=str(ROOT), env=env).returncode != 0:
        return 1
    spec = work / "fm-editor.spec"
    text = spec.read_text()
    if sys.platform.startswith("linux"):
        # Tk draws text through fontconfig. The build machine's is older
        # than the player's and chokes on its config files; every desktop
        # has fontconfig and FreeType, so the player's are used.
        assert "\npyz = " in text, "unexpected PyInstaller spec"
        text = text.replace("\npyz = ", "\na.binaries = [b for b in a.binaries\n"
                            "              if not b[0].startswith(('libfontconfig', 'libfreetype'))]\npyz = ", 1)
    if sys.platform == "win32":
        # The Python archive as fm-editor.pkg beside the .exe: a folder
        # build still appends it to the loader by default.
        assert "    exclude_binaries=True,\n" in text, "unexpected PyInstaller spec"
        text = text.replace("    exclude_binaries=True,\n", "    exclude_binaries=True,\n    append_pkg=False,\n", 1)
    spec.write_text(text)
    command = [sys.executable, "-m", "PyInstaller", *build, str(spec)]
    print(" ".join(command))
    result = subprocess.run(command, cwd=str(ROOT), env=env)
    if result.returncode == 0:
        built = dist / "fm-editor" / "fm-editor.exe" if sys.platform == "win32" else dist / "fm-editor"
        print(f"built {built}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
