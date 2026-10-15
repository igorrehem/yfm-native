#!/usr/bin/env python3
"""Check that the game's structures are laid out alike wherever a mod meets them.

Two pairs, one per mod target (--target, default both):

  i386            32-bit Linux against 32-bit Windows, below
  x86_64-windows  the 64-bit Windows game's view (x86_64-w64-mingw32, as
                  build_game32.py --target windows-x64 compiles it) against a
                  mod's (x86_64-w64-windows-gnu-elf, freestanding, as
                  build_mod.py --target x86_64-windows compiles it): the same
                  ABI in another object format, so every structure must come
                  out the same, G32 pointers 4 bytes on both sides

Both executables share one memory image with the retail game, and a code mod
is one object file for both (notes/portable-mods-plan.md), so every structure
in the headers must have the same size, alignment and field offsets on both.
They can differ: i386 Linux aligns `long long` and `double` to 4 inside a
structure and MinGW aligns them to 8 (as MIPS does), and MinGW packs
bitfields as MSVC does unless built with -mno-ms-bitfields.

Each header under src/ is compiled on its own by the same clang for
i386-pc-linux-gnu and for i686-w64-mingw32 (with the Windows build's
-mno-ms-bitfields), with clang's record layout dump, and the two dumps are
compared structure by structure. A header that does not compile on its own is
reported and skipped; one whose structures differ fails the check.

src/pc/platform and the native translated-runtime/ARM64-context headers are
left out: their host records are not shared guest layouts or part of the
portable i386 mod ABI."""
import argparse, concurrent.futures, glob, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import shutil
# The llvm-mingw build_win32_deps.py fetches, else one on PATH.
CLANG = next((path for path in (os.path.join(ROOT, "tmp/pc/llvm-mingw/bin/clang"),)
              if os.path.exists(path) or os.path.exists(path + ".exe")), None) or shutil.which("clang") or     os.path.join(ROOT, "tmp/pc/llvm-mingw/bin/clang")
FLAGS = ["-std=gnu11", "-fsyntax-only", "-w", "-DMEMORIES_PC", "-D_LANGUAGE_C", "-DLANGUAGE_C", "-Isrc",
         "-Xclang", "-fdump-record-layouts-complete", "-Xclang", "-fdump-record-layouts-simple"]
# The psyq headers expect the SDK's order (libgte.h, libgpu.h, libgs.h) and find one
# another with <angled> includes; a header that fails alone is tried again so.
PRELUDE = ["-isystem", "src/psyq", "-include", "src/psyq/libgte.h", "-include", "src/psyq/libgpu.h",
           "-include", "src/psyq/libgs.h"]
TARGETS = {"linux": ["--target=i386-pc-linux-gnu"], "windows": ["--target=i686-w64-mingw32", "-mno-ms-bitfields"],
           # The x86_64-windows pair: the game's flags (build_game32.py's
           # X64_FLAGS) and a mod's (build_mod.py's FLAGS64 and prelude).
           "x64-game": ["--target=x86_64-w64-mingw32", "-mno-ms-bitfields", "-fms-extensions",
                        "-include", "src/pc/compat/ptr32.h"],
           "x64-mod": ["--target=x86_64-w64-windows-gnu-elf", "-mno-ms-bitfields", "-fms-extensions",
                       "-ffreestanding", "-nostdinc", "-DMEMORIES_MOD", "-isystem", "src/pc/mods/sdk",
                       "-include", "src/pc/mods/prelude64.h"]}
PAIRS = {"i386": ("linux", "windows"), "x86_64-windows": ("x64-game", "x64-mod")}


TAGS = None  # struct and union tags defined under src/
PORT_PRIVATE = os.path.join("src", "pc", "platform") + os.sep
NATIVE_HEADERS = {
    os.path.join("src", "pc", "guest", "translated_runtime.h"),
    os.path.join("src", "pc", "guest", "state_arm64.h"),
}


def native_only(path):
    path = os.path.normpath(path)
    return path.startswith(PORT_PRIVATE) or path in NATIVE_HEADERS


def ours(name):
    """Whether a record is declared under src/ rather than in a system header,
    and the name to compare it by: an unnamed one's position, with the path
    spelled one way however it was reached."""
    unnamed = re.search(r"\(unnamed at ([^:]+)(:\d+:\d+)\)", name)
    if unnamed:
        path = os.path.relpath(os.path.normpath(os.path.join(ROOT, unnamed.group(1))), ROOT)
        if not path.startswith("src" + os.sep) or native_only(path):
            return None
        return name.replace(unnamed.group(0), f"(unnamed at {path}{unnamed.group(2)})")
    tag = name.split("::")[0].split()
    return name if len(tag) == 2 and tag[1] in TAGS else None


def layouts(header, target):
    """{record: its layout text} from one header, or None if it does not compile."""
    extra = ["-isystem", RESOURCE] if target == "x64-mod" else []
    for prelude in ([], PRELUDE):
        result = subprocess.run([CLANG, *TARGETS[target], *extra, *FLAGS, *prelude, "-include", header, "-x", "c",
                                 os.devnull], cwd=ROOT, capture_output=True, text=True)
        if not result.returncode:
            break
    else:
        return None
    found, name, lines = {}, None, []
    for line in result.stdout.splitlines():
        if line.startswith("*** Dumping AST Record Layout"):
            if name:
                found[name] = "\n".join(lines)
            name, lines = None, []
        elif line.startswith("Type: "):
            name = ours(line[len("Type: "):])
        elif name and line.strip() and not line.startswith("Layout: <ASTRecordLayout"):
            lines.append(line.strip())
    if name:
        found[name] = "\n".join(lines)
    return found


def check(job):
    header, pair = job
    first, second = (layouts(header, side) for side in PAIRS[pair])
    if first is None or second is None:
        return header, pair, None, []
    # A record only one side has is port code behind #ifdef _WIN32 (or,
    # for a mod, behind MEMORIES_MOD).
    return header, pair, len(first), [(name, first[name], second[name]) for name in sorted(first)
                                      if name in second and first[name] != second[name]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("headers", nargs="*", help="headers to check (default: every one under src/)")
    parser.add_argument("--verbose", action="store_true", help="show both layouts of every difference")
    parser.add_argument("--target", action="append", choices=list(PAIRS),
                        help="a mod target's pair to compare (repeatable; default: both)")
    options = parser.parse_args()
    if not os.path.exists(CLANG) and not os.path.exists(CLANG + ".exe"):
        sys.exit(f"{CLANG} is missing; run tools/pc/build_win32_deps.py first")
    global TAGS, RESOURCE
    RESOURCE = os.path.join(subprocess.run([CLANG, "-print-resource-dir"], capture_output=True, text=True).stdout.strip(),
                            "include")
    pairs = options.target or list(PAIRS)
    TAGS = set()
    for path in glob.glob("src/**/*.h", recursive=True, root_dir=ROOT):
        if native_only(path):
            continue
        with open(os.path.join(ROOT, path), errors="replace") as handle:
            TAGS.update(re.findall(r"\b(?:struct|union)\s+(\w+)\s*\{", handle.read()))
    headers = options.headers or sorted(path for path in glob.glob("src/**/*.h", recursive=True, root_dir=ROOT)
                                        if not native_only(path))
    failed = False
    for pair in pairs:
        skipped, records, differing = [], set(), {}
        with concurrent.futures.ThreadPoolExecutor(os.cpu_count()) as pool:
            for header, _, count, differences in pool.map(check, [(header, pair) for header in headers]):
                if count is None:
                    skipped.append(header)
                    continue
                records.add(header)
                for name, first, second in differences:
                    differing.setdefault(name, (header, first, second))
        sides = PAIRS[pair]
        for name, (header, first, second) in sorted(differing.items()):
            print(f"{name} ({header}) differs between {sides[0]} and {sides[1]}")
            if options.verbose:
                print(f"  {sides[0]}:\n    " + first.replace("\n", "\n    "))
                print(f"  {sides[1]}:\n    " + second.replace("\n", "\n    "))
        print(f"check_layouts: {pair}: {len(records)} headers compared, {len(skipped)} do not compile alone, "
              f"{len(differing)} structures differ")
        if skipped and options.verbose:
            print("  not compiled: " + " ".join(skipped))
        failed = failed or bool(differing)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
