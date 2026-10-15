#!/usr/bin/env python3
"""Build a code mod: every .c in its directory, merged into one object per
target (--target, default all three):

  i386            <library>.o, the 32-bit games' (Linux and Windows)
  x86_64-windows  <library>.x86_64-windows.o, the 64-bit Windows game's
  aarch64         <library>.aarch64.o, the arm64 (Android) game's

("library": "x" in mod.json; "x.o" names the same three. A "libraries"
object, {"x86_64-windows": "file.o", ...}, names a target's file outright,
as the game reads it: read_manifest in src/pc/mods/mods.c.)

The i386 object runs on both the Linux and the Windows game, which load it
with their own loader (src/pc/mods/object_loader.c), so a mod is built once,
on either system, with the same result. That only holds because the flags
below close every gap between the two 32-bit ABIs
(notes/portable-mods-plan.md):

  -fno-pic -fno-common            plain relocations only; no GOT, no COMMON
  -fno-stack-protector            the canary lives in Linux thread storage
  -march=i686 -mno-sse            x87 floating point, no SSE alignment needs
  -mstackrealign                  every function aligns its own stack to 16:
                                  Windows only promises 4 on the way in, and
                                  the Linux game (SSE2) needs 16 on the way
                                  out, or it faults on the first movaps
  -fstack-clash-protection        touches each stack page on the way down,
                                  as Windows' guard page requires
  -ffreestanding -nostdinc        no system C library: the SDK's headers
                                  (src/pc/mods/sdk) declare what the game lends
  -mretpoline-external-thunk      (clang; GCC: -mindirect-branch=thunk-extern
                                  -mindirect-branch-register) indirect calls go
                                  through the game's __x86_indirect_thunk_*,
                                  so a call through a guest function pointer
                                  works without DEP, as in the game's own code

The compiler is clang (on Windows, llvm-mingw's, targeting i386 Linux ELF),
else gcc -m32. MEMORIES_MOD_CC names another. The game's headers come from
src/ (in this repository) or from the sdk/include the game ships beside it,
where this script is sdk/tools/build_mod.py.

The 64-bit targets need clang (the same one builds all three) and differ:

  x86_64-windows  the Windows x64 calling convention in an ELF64 object
                  (--target=x86_64-w64-windows-gnu-elf: one loader reads
                  every target's objects); -mno-ms-bitfields, the game's
                  layouts
  aarch64         AAPCS64 as the Android game (aarch64-linux-android24 and
                  its flags), through tools/pc/ptr32_stores.py as every game
                  unit is (LLVM's AArch64 back end mis-sizes stores through a
                  4-byte pointer)
  both            -fms-extensions: the game's stored pointers stay 4 bytes
                  (G32, src/port_ptr.h); src/pc/mods/prelude64.h first, which
                  also declares the guest tables mods reach most, so a mod
                  that declares one itself without G32 does not compile; the
                  game's headers as system headers, and the mod's own pointer
                  and integer mix-ups (a pointer cast to a 32-bit int, a
                  pointer of another type) as errors, since on 64 bits they
                  lose half an address. A `.memories.abi` section names the
                  target, which the loader checks: x86-64 objects of the
                  Linux and of the Windows ABI look alike.

The names the mod leaves undefined are checked against what the game
provides: in the repository, each game build (--game, default both); beside
a game, the list its SDK was shipped with. A mod that would load on one
system and not the other fails here rather than in the game.

Objects are kept in tmp/pc/mod-build/<mod>-<key>, where the key is a digest
of everything that goes into the object: the compiler and linker (their
files), the flags, the include-path environment variables (ENVIRONMENT),
this script, and each source as the preprocessor sees
it, so with every header it includes (inputs_key). tmp is shared by every
checkout of the repository (the worktrees link it), and an object is reused
only where its inputs are the same, never because it is newer. A memo in
tmp/pc/mod-build/.memo finds the key again without the preprocessor while
none of the files it read has changed."""
import argparse, concurrent.futures, filecmp, functools, glob, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time
import build_process

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# In the repository, or the copy in the sdk/ directory beside a game
# (sdk/tools/build_mod.py, with the headers in sdk/include).
SHIPPED = not os.path.isdir(os.path.join(ROOT, "src/pc/mods/sdk"))
SDK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LLVM_MINGW = os.path.join(ROOT, "tmp/pc/llvm-mingw/bin")
CACHE = os.path.join(ROOT, "tmp", "pc", "mod-build")
TARGETS = ("i386", "x86_64-windows", "aarch64")
# The game builds a target's names are checked against (--game overrides);
# beside a game, the lists its SDK was shipped with.
TARGET_BUILDS = {"i386": ["tmp/pc/game32", "tmp/pc/win32"], "x86_64-windows": ["tmp/pc/win64"],
                 "aarch64": ["tmp/pc/android-arm64-v8a"]}
GAME_BUILDS = [SDK] if SHIPPED else [os.path.join(ROOT, path) for path in TARGET_BUILDS["i386"]]


def game_builds(target):
    return [SDK] if SHIPPED else [os.path.join(ROOT, path) for path in TARGET_BUILDS[target]]


FLAGS = ["-std=gnu11", "-O2", "-g", "-fno-pic", "-fno-pie", "-fno-common", "-fno-stack-protector",
         "-fno-asynchronous-unwind-tables", "-fno-unwind-tables", "-fstack-clash-protection",
         "-march=i686", "-mno-sse", "-mno-mmx", "-ffreestanding", "-nostdinc",
         "-DMEMORIES_PC", "-DMEMORIES_MOD", "-D_LANGUAGE_C", "-DLANGUAGE_C", "-Wall",
         "-Wno-unused-function", "-Wno-missing-braces"]
CLANG_FLAGS = ["--target=i386-pc-linux-gnu", "-mstackrealign", "-mretpoline-external-thunk"]
GCC_FLAGS = ["-m32", "-mstackrealign", "-mincoming-stack-boundary=2", "-mindirect-branch=thunk-extern",
             "-mindirect-branch-register"]
ENVIRONMENT = ["CPATH", "C_INCLUDE_PATH", "CCC_OVERRIDE_OPTIONS", "GCC_EXEC_PREFIX", "COMPILER_PATH"]
# The 64-bit targets (above): FLAGS without what is i386's own.
FLAGS64 = ["-std=gnu11", "-O2", "-g", "-fno-pic", "-fno-pie", "-fno-common", "-fno-stack-protector",
           "-fno-asynchronous-unwind-tables", "-fno-unwind-tables", "-ffreestanding", "-nostdinc",
           "-DMEMORIES_PC", "-DMEMORIES_MOD", "-D_LANGUAGE_C", "-DLANGUAGE_C", "-Wall",
           "-Wno-unused-function", "-Wno-missing-braces", "-fms-extensions", "-fno-jump-tables",
           "-Werror=incompatible-pointer-types", "-Werror=pointer-to-int-cast", "-Werror=int-to-pointer-cast",
           "-Werror=int-conversion"]
TARGET_FLAGS = {
    # The 64-bit Windows game's calling convention, layouts and indirect-branch
    # thunk (__x86_indirect_thunk_r11), in an ELF64 object.
    "x86_64-windows": ["--target=x86_64-w64-windows-gnu-elf", "-mretpoline-external-thunk", "-mno-ms-bitfields"],
    # The arm64 Android game's (build_android_deps.READY["arm64-v8a"] and
    # build_game32.py's arm64 flags): clang's SLS thunks as the indirect-branch
    # thunks, no fused multiply-add, MIPS's signed char.
    "aarch64": ["--target=aarch64-linux-android24", "-mharden-sls=blr", "-fno-optimize-sibling-calls",
                "-mno-outline-atomics", "-ffp-contract=off", "-fsigned-char"],
}


# The toolchain the game itself is built with, which has clang, ld.lld and
# llvm-objcopy and builds every target: the llvm-mingw release
# tools/pc/fetch_tools.py (Windows) and tools/pc/build_win32_deps.py (Linux)
# fetch. Named here for a modder who has none (toolchain_help), since the
# SDK ships neither script; test_build_mod_toolchain.py keeps them the same.
LLVM_MINGW_RELEASE = "20260922"
LLVM_MINGW_DOWNLOADS = {
    "windows": "https://github.com/mstorsjo/llvm-mingw/releases/download/20260922/"
               "llvm-mingw-20260922-ucrt-x86_64.zip",
    "linux": "https://github.com/mstorsjo/llvm-mingw/releases/download/20260922/"
             "llvm-mingw-20260922-ucrt-ubuntu-22.04-x86_64.tar.xz",
}
WIDE_TARGETS = ("x86_64-windows", "aarch64")


def tool(name):
    """A program from PATH, or from the llvm-mingw this repository fetches."""
    found = shutil.which(name)
    if not found and os.path.exists(os.path.join(LLVM_MINGW, name + (".exe" if os.name == "nt" else ""))):
        found = os.path.join(LLVM_MINGW, name)
    return found


def beside(program, name):
    """`name` in the folder of `program`, with Windows' .exe spelled out:
    "ld.lld" already has an extension, so none is added to it."""
    path = os.path.join(os.path.dirname(program), name)
    return next((p for p in (path + ".exe", path) if os.path.exists(p)), None)


def linker_for(clang):
    """The lld that came with `clang`, else one on PATH."""
    return beside(clang, "ld.lld") or tool("ld.lld")


def objcopy_for(clang):
    """llvm-objcopy beside `clang` and beside the clang a link points to
    (Debian's /usr/bin/clang is /usr/lib/llvm-NN/bin/clang, the only place
    its llvm-objcopy has no version suffix), then on PATH and in llvm-mingw."""
    for program in dict.fromkeys((clang, os.path.realpath(clang)) if clang else ()):
        found = beside(program, "llvm-objcopy")
        if found:
            return found
    return tool("llvm-objcopy")


def clang_candidates(named):
    """The compilers build_mod.py tries, in order (programs): `named`
    (MEMORIES_MOD_CC) alone when set."""
    return [named] if named else [os.path.join(LLVM_MINGW, "clang"), "clang", "gcc"]


def resolve(candidate):
    return candidate if os.path.isabs(candidate) and os.path.exists(candidate) else tool(candidate)


def missing_64bit():
    """What the 64-bit targets need that this machine lacks, by name: clang,
    ld.lld (beside it or on PATH) and llvm-objcopy. [] when all are here."""
    found = [path for path in map(resolve, clang_candidates(os.environ.get("MEMORIES_MOD_CC")))
             if path and "clang" in os.path.basename(path)]
    clang = next((path for path in found if linker_for(path)), found[0] if found else None)
    missing = [] if clang else ["clang"]
    if not (linker_for(clang) if clang else tool("ld.lld")):
        missing.append("ld.lld")
    if not objcopy_for(clang):
        missing.append("llvm-objcopy")
    return missing


def toolchain_help(missing, built=None, wanted=WIDE_TARGETS, compiler=True, outcome=True):
    """What to tell a modder whose 64-bit objects cannot be built: what is
    missing, what was built (with `outcome`: the i386 object at `built`, or
    nothing; with no compiler at all, `compiler` false, nothing), and where
    to get the toolchain the game is built with. No download here: the
    modder gets it."""
    named = os.environ.get("MEMORIES_MOD_CC")
    not_found = "Not found: " + ", ".join(missing)
    if named and "clang" in missing:
        not_found += f" (MEMORIES_MOD_CC names {named}, which is {'not clang' if resolve(named) else 'not there'})"
    games = {"x86_64-windows": "the 64-bit Windows game", "aarch64": "Android"}
    named_objects = ", ".join(f"{target}: {games[target]}" for target in wanted)
    if not compiler:
        lines = ["build_mod: nothing was built: no compiler found.",
                 "Every object builds with clang, ld.lld and llvm-objcopy; gcc with 32-bit support builds the "
                 f"32-bit one only. {not_found}."]
    else:
        lines = [f"build_mod: only the 32-bit object was built, {built} (the 32-bit Windows and Linux games)."
                 if built else "build_mod: nothing was built."] if outcome else []
        lines.append(f"The 64-bit object{'s' if len(wanted) > 1 else ''} ({named_objects}) "
                     f"need{'' if len(wanted) > 1 else 's'} clang with ld.lld and llvm-objcopy. {not_found}.")
    if sys.platform == "win32":
        lines += [f"Get llvm-mingw {LLVM_MINGW_RELEASE}, the toolchain the game is built with (it has all three):",
                  f"  {LLVM_MINGW_DOWNLOADS['windows']}",
                  "unzip it, put its bin folder on PATH (or set MEMORIES_MOD_CC to its bin\\clang.exe), "
                  "and run build_mod.py again."]
    elif sys.platform == "darwin":
        lines += ["Install them with Homebrew (brew install llvm lld), put $(brew --prefix llvm)/bin on PATH "
                  "(or set MEMORIES_MOD_CC to its clang), and run build_mod.py again."]
    else:
        lines += [f"Get llvm-mingw {LLVM_MINGW_RELEASE}, the toolchain the game is built with (Linux x86-64):",
                  f"  {LLVM_MINGW_DOWNLOADS['linux']}",
                  "and put its bin folder on PATH (or set MEMORIES_MOD_CC to its bin/clang); or install your "
                  "distribution's clang, lld and llvm (llvm-objcopy is in llvm):",
                  "  Debian/Ubuntu: sudo apt install clang lld llvm    Fedora: sudo dnf install clang lld llvm",
                  "  Arch: sudo pacman -S clang lld llvm",
                  "The 64-bit game is built with clang 21 or later (older ones are not verified with its 4-byte "
                  "pointers; clang 12 miscompiles them): prefer one that new. Then run build_mod.py again."]
    return "\n".join(lines)


def compiler(target="i386"):
    """(command, the compiler's own flags and headers for `target`, linker
    command); target_flags adds the rest."""
    path, clang, linker = programs()
    if target == "i386":
        return [path], (CLANG_FLAGS if clang else GCC_FLAGS) + ["-isystem", builtin_headers(path, clang)], list(linker)
    if not clang:
        sys.exit(f"build_mod: the {target} object needs clang (with lld); {path} is not clang\n" +
                 toolchain_help(missing_64bit() or ["clang"], wanted=(target,), outcome=False))
    return [path], TARGET_FLAGS[target] + ["-isystem", builtin_headers(path, clang)], list(linker)


def target_flags(target, cc_flags):
    """Every flag a unit is compiled with for `target`, before the mod's own
    (-I <its directory>): the i386 list exactly as it has always been."""
    if target == "i386":
        return FLAGS + cc_flags + headers()
    return FLAGS64 + cc_flags + headers(system=True) + [
        "-include", os.path.join(include_root(), "pc", "mods", "prelude64.h")]


def programs():
    """(compiler, whether it is clang, linker command), found without
    starting either: the cache keys need only their files."""
    found = find_programs(os.environ.get("MEMORIES_MOD_CC"))
    if not found:
        sys.exit(toolchain_help(missing_64bit(), compiler=False))
    return found


@functools.lru_cache(maxsize=None)
def find_programs(named):
    for candidate in clang_candidates(named):
        path = resolve(candidate)
        if not path:
            continue
        if "clang" in os.path.basename(path):
            linker = linker_for(path)
            if not linker:
                continue  # clang without lld cannot merge the objects; try the next compiler
            return path, True, (linker, "-r")
        return path, False, (tool("ld") or "ld", "-m", "elf_i386", "-r")
    return None


@functools.lru_cache(maxsize=None)
def builtin_headers(path, clang):
    """The compiler's own headers (stddef.h, stdarg.h and the like)."""
    if clang:
        resource = subprocess.run([path, "-print-resource-dir"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
        return os.path.join(resource, "include")
    return subprocess.run([path, "-m32", "-print-file-name=include"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()


def include_root():
    """Where the game's headers are: src/, or the SDK's include/."""
    return os.path.join(SDK, "include") if SHIPPED else os.path.join(ROOT, "src")


def headers(system=False):
    """The SDK's C library, then the game's headers (as system headers for
    the 64-bit targets: their warnings are the game's; the mod's own are
    errors there)."""
    libc = os.path.join(SDK, "include", "libc") if SHIPPED else os.path.join(ROOT, "src/pc/mods/sdk")
    return ["-isystem", libc, "-isystem" if system else "-I", include_root()]


def run(command):
    result = build_process.run(command)
    if result.returncode:
        sys.exit(f"build_mod: {' '.join(command[:3])} ... failed\n{result.stdout}{result.stderr}")
    return result.stdout


def provided(build, target="i386"):
    """The names a game build of `target` lends mods: its export table and
    the C library list, or None if that build is not there. A game build in
    the repository has its generated table; an SDK beside a game has the
    list it was shipped with (exports.<target>.txt; a 32-bit game's is also
    exports.txt, the one name SDKs had before the 64-bit targets)."""
    table = os.path.join(build, "mod_exports.c")
    if os.path.exists(table):
        with open(table) as handle:
            names = set(re.findall(r'^    \{"([^"]+)"', handle.read(), re.M))
        return names | libc_names(target)
    for shipped in [os.path.join(build, f"exports.{target}.txt")] + \
            ([os.path.join(build, "exports.txt")] if target == "i386" else []):
        if os.path.exists(shipped):
            with open(shipped) as handle:
                return set(handle.read().split())
    return None


def libc_names(target="i386"):
    """The C library list in src/pc/mods/mod_libc.c for `target`: the names
    every target has, and those of its own block (`#if defined(__i386__)`,
    `#elif defined(__x86_64__) ...`)."""
    with open(os.path.join(ROOT, "src/pc/mods/mod_libc.c")) as handle:
        text = handle.read()
    table = text[text.index("functions[] = {"):]
    table = table[:table.index("};")]
    names, block = set(), None
    for line in table.splitlines():
        stripped = line.strip()
        if stripped.startswith(("#if", "#elif")):
            block = ("i386" if "__i386__" in stripped else "x86_64-windows" if "__x86_64__" in stripped
                     else "aarch64" if "__aarch64__" in stripped else "?")
            continue
        if stripped.startswith("#endif"):
            block = None
            continue
        if block in (None, target):
            # F(name), or AS(name, function) for one the host implements itself.
            names.update(re.findall(r"\b(?:F\(|AS\()(\w+)\b", line))
    return names


def library_name(directory, target="i386"):
    """The object's file name for `target`, relative to the mod's directory,
    by the game's own rule (read_manifest in src/pc/mods/mods.c): the
    target's entry in "libraries" as written; else from "library", for
    i386 as written when it has a '.' anywhere in it (else with ".o"
    added) and for the others <library>.<target>.o, a ".o" taken off first.
    A mod with "libraries" and no "library" goes by its id. The game loads
    no code for a mod with neither, so neither is one built."""
    manifest = os.path.join(directory, "mod.json")
    if not os.path.exists(manifest):
        sys.exit(f"{directory}: no mod.json (notes/modding.md)")
    # utf-8-sig: a manifest saved with a byte order mark, as the game allows.
    with open(manifest, encoding="utf-8-sig") as handle:
        data = json.load(handle)
    libraries = data.get("libraries")
    named = libraries.get(target) if isinstance(libraries, dict) else None
    if isinstance(named, str) and named:
        return named
    name = data.get("library")
    if not name and isinstance(libraries, dict) and libraries:
        name = data.get("id") or os.path.basename(os.path.normpath(directory))
    if not name:
        sys.exit(f'{manifest}: the mod has C sources but no "library": the game would load none of its code. '
                 f'Add "library": "{os.path.basename(os.path.normpath(directory))}"')
    if target == "i386":
        return name if "." in name else name + ".o"
    stem = name[:-2] if len(name) > 2 and name.endswith(".o") else name
    return f"{stem}.{target}.o"


def identity(program):
    """A compiler or linker as the keys know it: its file's name, size and
    time, as ccache's compiler_check=mtime does, so no process starts. The
    same file through another worktree's junction is the same file."""
    found = program if os.path.dirname(program) else shutil.which(program)
    for candidate in (found, found + ".exe") if found else ():
        if os.path.isfile(candidate):
            real = os.path.realpath(candidate)
            stat = os.stat(real)
            return f"{os.path.basename(real)} {stat.st_size} {stat.st_mtime_ns}"
    sys.exit(f"build_mod: {program} not found")


def portable(text):
    """`text` with this checkout's root spelled the same in every checkout."""
    for root in sorted({ROOT, ROOT.replace("\\", "/"), ROOT.replace("/", "\\")}, key=len, reverse=True):
        text = text.replace(root, "<root>")
    return text


def file_digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def script_digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read().replace(b"\r\n", b"\n")).hexdigest()   # either checkout's line ends


def settings_digest(directory, extra_flags, target="i386"):
    """What both of an object's digests start from: this script, the
    compiler and linker, the target, the flags and the library name, and for
    aarch64 the IR pass every unit goes through."""
    path, clang, linker = programs()
    if target == "i386":
        flags = FLAGS + (CLANG_FLAGS if clang else GCC_FLAGS) + headers() + list(extra_flags)
    else:
        flags = target_flags(target, TARGET_FLAGS[target]) + list(extra_flags)
    digest = hashlib.sha256()
    script = script_digest(os.path.abspath(__file__))
    # What the compiler reads from the environment that can change the
    # object: CPATH and C_INCLUDE_PATH add include directories even with
    # -nostdinc, so a memo would otherwise find the key of other headers.
    environment = "\n".join(f"{name}={os.environ.get(name, '')}" for name in ENVIRONMENT)
    parts = [("script", script), ("compiler", identity(path)), ("linker", identity(linker[0])),
             ("flags", portable("\n".join(flags))), ("library", library_name(directory, target)),
             ("environment", environment)]
    if target != "i386":   # the i386 keys stay what they were
        parts.append(("target", target))
    if target == "aarch64":
        parts.append(("pass", script_digest(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                         "ptr32_stores.py"))))
    for label, text in parts:
        digest.update(f"{label}\0{text}\0".encode("utf-8", "surrogateescape"))
    return digest


# A line marker in preprocessed C: # <line> "<file>" <flags>. The key keeps
# the line, which the debug information records, and drops the file, which
# names the checkout; the file goes in the memo's list instead.
LINE_MARKER = re.compile(rb'^(#(?: line)? \d+) "((?:[^"\\]|\\.)*)"', re.M)


def inputs_key(directory, sources, extra_flags, into, target="i386"):
    """The key an object is kept under in tmp/pc/mod-build: settings_digest
    and each source after the preprocessor, which takes in every header it
    includes from wherever it is. The preprocessed sources are written to
    `into` (<source>.i), and publish compiles those, not the sources: the
    object is made of exactly what the key was taken from, even when a
    header changes while the mod builds. No time goes into the key: another
    checkout sharing tmp gets the same object only when it has the same
    inputs. Returns (key, the preprocessed files, the files the
    preprocessor read, or None when one of them cannot be named, and when
    it started)."""
    cc, cc_flags, _ = compiler(target)
    flags = target_flags(target, cc_flags) + list(extra_flags)
    digest = settings_digest(directory, extra_flags, target)
    started = time.time()
    preprocessed = [os.path.join(into, os.path.basename(source) + ".i") for source in sources]
    with concurrent.futures.ThreadPoolExecutor(len(sources)) as pool:
        list(pool.map(lambda pair: run(cc + flags + ["-E", pair[0], "-o", pair[1]]), zip(sources, preprocessed)))
    read, unnamed = set(), False
    for source, path in zip(sources, preprocessed):
        with open(path, "rb") as handle:
            text = handle.read().replace(b"\r\n", b"\n")   # clang on Windows writes CRLF
        for match in LINE_MARKER.finditer(text):
            if match.group(2).startswith(b"<"):
                continue   # <built-in>, <command line>
            name = os.path.normpath(os.path.abspath(
                re.sub(rb"\\(.)", rb"\1", match.group(2)).decode("utf-8", "surrogateescape")))
            if os.path.isfile(name):
                read.add(name)
            elif not os.path.isdir(name):   # GCC names the working directory with -g
                unnamed = True   # a file the memo could not watch: no memo
        digest.update(os.path.basename(source).encode() + b"\0" + LINE_MARKER.sub(rb"\1", text) + b"\0")
    return digest.hexdigest(), preprocessed, None if unnamed else read, started


# The memo: the key inputs_key gave, remembered with the content of every
# file the preprocessor read, so that a build with none of them changed
# finds the key again without starting the preprocessor (as ccache's direct
# mode). It is only a way to the key, never to an object: a memo that does
# not hold sends the build to inputs_key. The memos are in
# tmp/pc/mod-build/.memo.


def memo_folder(directory, sources, extra_flags, target="i386"):
    """Where the memos for these sources are: named by settings_digest, the
    sources and the names of every file that could be included (in the
    game's headers or the SDK's, and in the mod's directory), so that a new
    file that would be found first, and so was never read, also misses."""
    digest = settings_digest(directory, extra_flags, target)
    for source in sources:
        digest.update(os.path.basename(source).encode() + b"\0" + file_digest(source).encode() + b"\0")
    include = os.path.join(SDK, "include") if SHIPPED else os.path.join(ROOT, "src")
    names = glob.glob(os.path.join(include, "**", "*"), recursive=True)
    # Not the objects build_mod.py writes beside the sources by default.
    outputs = {os.path.abspath(os.path.join(directory, library_name(directory, each))) for each in TARGETS}
    names += [name for name in glob.glob(os.path.join(directory, "**", "*"), recursive=True)
              if os.path.abspath(name) not in outputs]
    listing = "\n".join(sorted(portable(os.path.abspath(name)) for name in names))
    digest.update(listing.encode("utf-8", "surrogateescape"))
    return os.path.join(CACHE, ".memo", f"{os.path.basename(os.path.abspath(directory))}-{digest.hexdigest()[:24]}")


def recall(folder):
    """The key of a memo in `folder` whose files are all as they were."""
    for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
        try:
            with open(path, encoding="utf-8") as handle:
                memo = json.load(handle)
            if all(file_digest(name.replace("<root>", ROOT)) == digest for name, digest in memo["files"].items()):
                try:
                    os.utime(folder)   # in use: kept by prune
                except OSError:
                    pass
                return memo["key"]
        except (OSError, ValueError, KeyError, AttributeError):
            continue   # a file gone, or a memo from another version of this script
    return None


def remember(folder, key, read, started):
    if read is None:
        return
    files = {}
    try:
        for path in sorted(read):
            if os.path.getmtime(path) >= started:
                return   # changed while the preprocessor ran: the key may not be of what is there now
            files[portable(path)] = file_digest(path)
        os.makedirs(folder, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=folder, suffix=".tmp")
    except OSError:
        # A header gone since the preprocessor read it (a checkout while the
        # mod builds), or the folder pruned by another build just now.
        return
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump({"key": key, "files": files}, stream, indent=0)
        os.replace(temporary, os.path.join(folder, key[:16] + ".json"))
    except OSError:
        # Windows will not replace a file another build is reading (recall),
        # and that file is this same memo. A memo is only a shortcut.
        try:
            os.remove(temporary)
        except OSError:
            pass


def compile_object(sources, output, objects_dir, extra_flags=(), target="i386"):
    """Compile `sources` with the mod flags for `target` (then `extra_flags`,
    which the loader's tests use to make broken objects) and merge them into
    `output`; a 64-bit object gets its `.memories.abi` section."""
    cc, cc_flags, linker = compiler(target)
    flags = target_flags(target, cc_flags)
    objects = []
    os.makedirs(objects_dir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    clang = programs()[1]
    for source in sources:
        obj = os.path.join(objects_dir, os.path.basename(source) + ".o")
        # clang names the compile unit after the file it compiles, here the
        # preprocessed copy in a staging folder that is gone a moment later
        # (and has a random name, so no two builds were the same bytes).
        # Given that same path as the main file name, it takes the name in
        # the first line marker instead, the source's, as GCC does.
        named = ["-Xclang", "-main-file-name", "-Xclang", source] if clang and "cpp-output" in extra_flags else []
        if target == "aarch64":
            through_pass(cc + flags + [*extra_flags, *named], source, obj)
        else:
            run(cc + flags + [*extra_flags, *named, "-c", source, "-o", obj])
        objects.append(obj)
    run(linker + ["-o", output] + objects)
    if target != "i386":
        tag_abi(output, target)
    return output


def through_pass(command, source, obj):
    """An aarch64 unit as the arm64 game's are (build_game32.py's
    compile_unit): to IR, every store through a 4-byte pointer sent through
    an ordinary one (tools/pc/ptr32_stores.py), then to the object."""
    import ptr32_stores
    ir = obj[:-2] + ".ll"
    run(command + ["-S", "-emit-llvm", "-Xclang", "-disable-llvm-passes", source, "-o", ir])
    with open(ir, encoding="utf-8") as handle:
        text = handle.read()
    try:
        text = ptr32_stores.rewrite(text)
    except ValueError as error:
        sys.exit(f"build_mod: {source}: {error}")
    with open(ir, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    # The IR is compiled with the unit's flags less the language's (it is
    # LLVM IR now, not C or preprocessed C).
    flags = [flag for flag in command[1:] if flag not in ("-x", "cpp-output", "c")]
    run([command[0], *flags, "-Wno-unused-command-line-argument", "-x", "ir", "-c", ir, "-o", obj])


@functools.lru_cache(maxsize=None)
def find_objcopy():
    """llvm-objcopy for the compiler in use (objcopy_for), or None."""
    path, clang, _ = programs()
    return objcopy_for(path if clang else None)


def tag_abi(output, target):
    """The `.memories.abi` section: the target's name, NUL-terminated, which
    the game's loader holds against its own (object_loader.c)."""
    objcopy = find_objcopy()
    if not objcopy:
        sys.exit("build_mod: llvm-objcopy (beside clang, or on PATH) is needed for the 64-bit targets\n" +
                 toolchain_help(["llvm-objcopy"], wanted=(target,), outcome=False))
    with tempfile.NamedTemporaryFile("wb", suffix=".abi", delete=False) as handle:
        handle.write(target.encode() + b"\0")
    try:
        run([objcopy, "--add-section", f".memories.abi={handle.name}", output])
    finally:
        os.remove(handle.name)


def build(directory, out_dir=None, objects_dir=None, extra_flags=(), games=None, quiet=False, target="i386"):
    """Build the mod in `directory` for `target`; returns the path of its
    object, or None when it has no C (a data-only mod). The object is built
    once per inputs_key, into tmp/pc/mod-build/<mod>-<key>, and copied to
    `out_dir` (default: the mod's directory) when what is there differs. It
    is checked against the target's game builds (`games`, default
    game_builds(target)) every time, reused or not: what a game lends comes
    from the game's own sources, which the key does not cover."""
    sources = sorted(glob.glob(os.path.join(directory, "*.c")))
    if not sources:
        return None
    prune()
    if games is None:
        games = game_builds(target)
    name = library_name(directory, target)
    output = os.path.join(out_dir or directory, name)
    extra_flags = ["-I", directory, *extra_flags]
    mod = os.path.basename(os.path.abspath(directory))
    memo = memo_folder(directory, sources, extra_flags, target)
    key = recall(memo)
    state = "up to date"
    try:
        if key is None or not os.path.exists(os.path.join(CACHE, f"{mod}-{key[:16]}", name)):
            # The key again from the preprocessor: a memo is never trusted to
            # say what an object is made of, only that it is already built.
            os.makedirs(CACHE, exist_ok=True)
            stage = tempfile.mkdtemp(prefix=f".{mod}-", dir=CACHE)
            try:
                parts = os.path.join(stage, "parts")
                os.makedirs(parts)
                key, preprocessed, read, started = inputs_key(directory, sources, extra_flags, parts, target)
                remember(memo, key, read, started)
                entry = os.path.join(CACHE, f"{mod}-{key[:16]}")
                if not os.path.exists(os.path.join(entry, name)):
                    publish(entry, name, stage, preprocessed, objects_dir or parts, extra_flags, games, target)
                    state = f"{len(sources)} source{'s' if len(sources) != 1 else ''}"
            finally:
                shutil.rmtree(stage, ignore_errors=True)
        entry = os.path.join(CACHE, f"{mod}-{key[:16]}")
        cached = os.path.join(entry, name)
        if state == "up to date":
            try:
                with open(cached + ".undefined") as handle:
                    undefined = set(handle.read().split())
            except OSError:
                undefined = None
            checked = check(cached, games, undefined, target)
        else:   # publish checked it
            checked = any(provided(build, target) is not None for build in games)
    except SystemExit:
        if os.path.exists(output):
            os.remove(output)   # not left there to pass for this mod's object
        raise
    if not os.path.exists(output) or not filecmp.cmp(cached, output, shallow=False):
        os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)   # "library": "sub/rules"
        shutil.copyfile(cached, output)
    if not quiet:
        unchecked = "" if checked else f"; not checked: no {target} game build or exports list was found"
        print(f"{output}: {state} ({os.path.relpath(entry, ROOT)}){unchecked}")
    return output


def publish(entry, name, stage, preprocessed, objects_dir, extra_flags, games, target="i386"):
    """Compile the preprocessed sources into `stage`, check the object, and
    rename its folder to `entry`: a folder there is always a whole object
    that passed, with the names it leaves undefined beside it
    (<library>.undefined). When another checkout gets there first with the
    same key, its object is the same and this one is dropped."""
    staged = os.path.join(stage, "object")
    output = compile_object(preprocessed, os.path.join(staged, name), objects_dir,
                            [*extra_flags, "-x", "cpp-output"], target)
    undefined = undefined_names(output)
    check(output, games, undefined, target)
    with open(output + ".undefined", "w") as handle:
        handle.writelines(symbol + "\n" for symbol in sorted(undefined))
    for attempt in range(40):
        try:
            os.rename(staged, entry)
            return
        except OSError:
            if os.path.exists(os.path.join(entry, name)):
                return
            if os.path.isdir(entry):
                shutil.rmtree(entry, ignore_errors=True)   # emptied by hand: not an object
            if attempt == 39:
                raise
            time.sleep(0.25)   # a virus scanner still holding the new file (Windows)


@functools.lru_cache(maxsize=None)
def prune():
    """Once per process: drop what nothing will use. A staging folder
    (.<mod>-XXXX) a day old is from a build that was stopped; a memo folder
    no build has found a key in for 30 days is from sources that are gone.
    Objects stay: each is small, and one may be about to be copied."""
    now = time.time()
    for path in glob.glob(os.path.join(CACHE, ".*-*")) + glob.glob(os.path.join(CACHE, ".memo", "*")):
        try:
            age = now - os.path.getmtime(path)
        except OSError:
            continue
        if age > (30 if os.path.basename(os.path.dirname(path)) == ".memo" else 1) * 86400:
            shutil.rmtree(path, ignore_errors=True)


def undefined_names(output):
    """The names the object leaves for the game to lend."""
    reader = tool("llvm-readelf") or tool("readelf")
    undefined = set()
    for line in run([reader, "-sW", output]).splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[6] == "UND" and parts[4] != "WEAK":
            undefined.add(parts[7])
    return undefined


def check(output, games, undefined=None, target="i386"):
    """What the object leaves undefined must be there on every game build
    of its target. Returns whether any build (or list) was there to check
    against."""
    if undefined is None:
        undefined = undefined_names(output)
    for bad, why in (("_GLOBAL_OFFSET_TABLE_", "it is position-independent"),
                     ("__stack_chk_fail", "it uses the stack protector"),
                     ("__stack_chk_fail_local", "it uses the stack protector")):
        if bad in undefined:
            sys.exit(f"build_mod: {output}: {why}; build it with the flags in this script")
    checked = False
    for build in games:
        names = provided(build, target)
        if names is None:
            continue
        checked = True
        missing = sorted(undefined - names)
        if missing:
            try:
                build = os.path.relpath(build, ROOT)
            except ValueError:
                pass   # on another drive (Windows)
            sys.exit(f"build_mod: {output} needs names the game at {build} "
                     f"does not provide: {' '.join(missing)}")
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", help="the mod's directory (its mod.json and .c files)")
    parser.add_argument("--out", help="where the objects go (default: the mod's directory)")
    parser.add_argument("--target", action="append", choices=TARGETS + ("macos",),
                        help="a target to build for (repeatable; default: all three ELF targets, or i386 alone "
                             "when the compiler is gcc). macos is the translated macOS ARM64 dylib "
                             "(build_mod_arm64.py), built only when named")
    parser.add_argument("--game", action="append",
                        help="a game build directory to check the mod's names against (repeatable, for one "
                             "--target; default: the target's builds in tmp/pc when they exist)")
    options = parser.parse_args()
    if not glob.glob(os.path.join(options.directory, "*.c")):
        print(f"{options.directory}: no C sources; a data-only mod needs no build")
        return
    # The 64-bit targets need clang with ld.lld and llvm-objcopy. Not asked
    # for by name, they are left out without them: the i386 object is built,
    # as before there were others, and the modder told what to get.
    wide = programs()[1] and find_objcopy()
    asked = [target for target in options.target or () if target in WIDE_TARGETS]
    if asked and not wide:
        sys.exit(toolchain_help(missing_64bit() or ["llvm-objcopy"], wanted=asked))
    targets = options.target or (list(TARGETS) if wide else ["i386"])
    if options.game and len(targets) != 1:
        parser.error("--game checks one target's names: name it with --target")
    for target in targets:
        if target == "macos":
            from build_mod_arm64 import build as build_arm64_mod
            build_arm64_mod(options.directory, options.out,
                            game=options.game[0] if options.game else None)
            continue
        output = build(options.directory, options.out, games=options.game, target=target)
        if not output:
            print(f"{options.directory}: no C sources; a data-only mod needs no build")
            break
        if not options.target and not wide:
            print(toolchain_help(missing_64bit() or ["llvm-objcopy"], built=output), file=sys.stderr)


if __name__ == "__main__":
    main()
