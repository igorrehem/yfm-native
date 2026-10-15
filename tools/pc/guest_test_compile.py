"""Compile guest fixtures with pinned LLVM; host harnesses own sanitizers.

Apple Clang 17 cannot preserve AArch64 __ptr32 layouts or consume every
LLVM 21 IR dialect feature. Pass native objects across this compiler boundary.
LLVM 21's ASan ABI/runtime is incompatible with the Apple runtime used by
these harnesses, so guest objects are unsanitized; host harnesses and memory
resolvers retain ASan/UBSan coverage. Guest accesses have separate IR canaries.
"""

import os
import subprocess

from llvm_guest import ROOT, toolchain


def host_compiler(*, sanitize=False):
    """Guest LLVM stays pinned; host ASan uses Apple's compatible runtime."""
    return os.environ.get("CC") or (
        "/usr/bin/clang" if sanitize else str(toolchain() / "bin/clang")
    )


def guest_object(source, output, flags):
    guest_flags = [flag for flag in flags if not flag.startswith("-fsanitize=")]
    subprocess.run(
        [
            str(toolchain() / "bin/clang"),
            *guest_flags,
            "-c",
            str(source),
            "-o",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        timeout=60,
    )
    return str(output)


def run_fixture(
    out, guest_sources, host_sources, flags, link_flags=(), *, compiler=None
):
    """Use pinned guest objects with the selected host/sanitizer runtime."""
    objects = [
        guest_object(source, out / f"guest-{index}.o", flags)
        for index, source in enumerate(guest_sources)
    ]
    binary = out / "test"
    subprocess.run(
        [
            compiler
            or host_compiler(
                sanitize=any(flag.startswith("-fsanitize=") for flag in flags)
            ),
            *flags,
            *objects,
            *map(str, host_sources),
            *link_flags,
            "-o",
            str(binary),
        ],
        cwd=ROOT,
        check=True,
        timeout=60,
    )
    subprocess.run([str(binary)], cwd=ROOT, check=True, timeout=30)
    return binary


PS1_TARGETS = {
    "console": ["--target=mipsel-none-elf"],
    "linux": ["--target=i386-pc-linux-gnu", "-DMEMORIES_PC"],
    "windows": ["--target=i686-w64-mingw32", "-DMEMORIES_PC", "-mno-ms-bitfields"],
    "windows-x64": [
        "--target=x86_64-w64-mingw32",
        "-DMEMORIES_PC",
        "-mno-ms-bitfields",
    ],
    "android-arm64": ["--target=aarch64-linux-android", "-DMEMORIES_PC"],
    "macos": ["--target=aarch64-apple-darwin", "-DMEMORIES_PC"],
}
