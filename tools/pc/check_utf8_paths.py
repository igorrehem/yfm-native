#!/usr/bin/env python3
"""Every native unit that names a file reaches the UTF-8 boundary.

On Windows the C runtime's fopen/opendir/stat/getenv and FreeType's
FT_New_Face take the ANSI code page, so a folder named with accents
("Área de Trabalho", a user name like "José") cannot be opened through them.
src/pc/compat/fs.h turns those calls into the wide ones and compat/font.h
loads FreeType faces from memory (notes/pc-build.md, "Folder names"). A unit
that calls them without reaching the header compiles and works everywhere
but under such a folder, which is how mod text and fonts broke once
(translation.c, glyphs.c). This reads the sources, so it runs on any host.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit import mask_noncode  # noqa: E402

# What fs.h renames (its #define list), called as functions.
WRAPPED = ("fopen", "open", "access", "mkdir", "rmdir", "remove", "unlink", "rename", "readlink",
           "stat", "getenv", "setenv", "unsetenv", "mkstemp", "mkdtemp", "opendir")
# Narrow calls fs.h does not cover: each one misses the wide API on Windows.
NARROW = ("freopen", "fopen_s", "_fopen", "_open", "_mkdir", "_rmdir", "_access", "_stat", "_stat64",
          "_unlink", "_chdir", "_getcwd", "CreateFileA", "LoadLibraryA", "LoadLibraryExA", "FindFirstFileA",
          "GetModuleFileNameA", "ShellExecuteA", "CreateProcessA", "GetFileAttributesA",
          "png_image_begin_read_from_file", "png_image_write_to_file", "stb_vorbis_open_filename",
          "stb_vorbis_decode_filename")
# Called through a pointer or as a member, or defined by the unit itself.
CALL = re.compile(r"(?<![\w.>])(%s)\s*\(" % "|".join(WRAPPED + NARROW + ("FT_New_Face",)))
INCLUDE = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.M)
SKIP = ("src/pc/third_party/", "src/pc/compat/fs.c")


def includes(path: Path, seen: set[Path]) -> set[Path]:
    """The quoted headers a file reaches, whatever #if surrounds them."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return seen
    for name in INCLUDE.findall(text):
        for base in (path.parent, ROOT / "src"):
            header = (base / name).resolve()
            if header.is_file():
                if header not in seen:
                    seen.add(header)
                    includes(header, seen)
                break
    return seen


def problems(path: Path) -> list[str]:
    code = mask_noncode(path.read_text(encoding="utf-8", errors="replace"))
    calls: dict[str, int] = {}
    for match in CALL.finditer(code):
        line = code.count("\n", 0, match.start()) + 1
        calls.setdefault(match[1], line)
    if not calls:
        return []
    reached = {h.relative_to(ROOT).as_posix() for h in includes(path, set()) if ROOT in h.parents}
    found = []
    for name, line in sorted(calls.items(), key=lambda item: item[1]):
        if name in NARROW:
            found.append(f"{line}: {name}() takes the ANSI code page on Windows; use the fs.h calls")
        elif name == "FT_New_Face" and "src/pc/compat/font.h" not in reached:
            found.append(f"{line}: FT_New_Face() without pc/compat/font.h (FreeType opens with ANSI fopen)")
        elif name != "FT_New_Face" and "src/pc/compat/fs.h" not in reached:
            found.append(f"{line}: {name}() without pc/compat/fs.h (or posix.h/font.h)")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", default=["src/pc"],
                        help="source folders or files, from the repository root (default: src/pc)")
    args = parser.parse_args()
    units: list[Path] = []
    for name in args.paths:
        path = (ROOT / name).resolve()
        units.extend(sorted(path.rglob("*.c")) if path.is_dir() else [path])
    failed = checked = 0
    for unit in units:
        relative = unit.relative_to(ROOT).as_posix()
        if relative.startswith(SKIP):
            continue
        checked += 1
        for problem in problems(unit):
            print(f"{relative}:{problem}")
            failed += 1
    if failed:
        print(f"{failed} call(s) bypass the UTF-8 file boundary (notes/pc-build.md, \"Folder names\")")
        return 1
    print(f"{checked} units reach the UTF-8 file boundary")
    return 0


if __name__ == "__main__":
    sys.exit(main())
