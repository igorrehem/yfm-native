"""Build isolated guest IR fixtures from current sources, without a game build."""

import subprocess
from pathlib import Path

from guest_build import guest_frontend_flags
from guest_test_compile import host_compiler, run_fixture
from llvm_guest import ROOT, normalize, toolchain
from macos_deps import sdk_path


def read_guest_source(source, out):
    source = Path(source)
    if not source.is_absolute():
        source = ROOT / source
    raw = out / (source.relative_to(ROOT).as_posix().replace("/", "_") + ".ll")
    flags = [*guest_frontend_flags(sdk_path()), "-fcommon", "-w"]
    if source.is_relative_to(ROOT / "src/game") or source.is_relative_to(
        ROOT / "src/overlays"
    ):
        flags += ["-include", str(ROOT / "src/pc/compat/pgxp_game.h")]
    subprocess.run(
        [
            str(toolchain() / "bin/clang"),
            *flags,
            "-S",
            "-emit-llvm",
            str(source),
            "-o",
            str(raw),
        ],
        cwd=ROOT,
        check=True,
        timeout=60,
    )
    return normalize(raw.read_text())


def select_functions(text, selected):
    return normalize(text, keep_functions=selected)


def run_translated_fixture(units, harness, out, *, sanitize=False, extra_sources=()):
    """Pinned guest objects; host units use Apple's sanitizer runtime."""
    flags = [
        "-isysroot",
        str(sdk_path()),
        "-O2",
        "-std=gnu11",
        "-DMEMORIES_PC",
        "-DMEMORIES_TRANSLATED",
        "-fms-extensions",
        "-I" + str(ROOT / "src"),
        "-w",
    ]
    if sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    host_sources = [
        ROOT / "src/pc/memory.c",
        ROOT / "src/pc/guest/translated_runtime.c",
    ]
    return run_fixture(
        out,
        [*units, harness],
        [*extra_sources, *host_sources],
        flags,
        compiler=host_compiler(sanitize=sanitize),
    )
