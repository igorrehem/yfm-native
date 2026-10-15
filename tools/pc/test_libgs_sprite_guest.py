#!/usr/bin/env python3
"""Compile and execute the real LIBGS sprite renderer without a disc."""

import argparse
import subprocess

from guest_test_compile import guest_object, host_compiler
from llvm_guest import ROOT, toolchain, translate
from macos_deps import sdk_path
from translate_guest_ir import address_map


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    out = ROOT / "tmp/libgs-sprite-test"
    out.mkdir(parents=True, exist_ok=True)
    compiler = str(toolchain() / "bin/clang")
    flags = [
        "-std=gnu11",
        "-DMEMORIES_PC",
        "-DMEMORIES_TRANSLATED",
        "-fms-extensions",
        "-Isrc",
        "-isysroot",
        str(sdk_path()),
        "-Wno-incompatible-pointer-types",
        "-Wno-incompatible-library-redeclaration",
    ]
    raw = out / "libgs.raw.ll"
    subprocess.run(
        [
            compiler,
            *flags,
            "-O0",
            "-S",
            "-emit-llvm",
            "src/pc/sdk/libgs.c",
            "-o",
            str(raw),
        ],
        cwd=ROOT,
        check=True,
        timeout=60,
    )
    adapted = out / "libgs.ll"
    adapted.write_text(
        translate(raw.read_text(), address_map(ROOT / "config/pc/guest_addresses.txt"))
    )
    host = host_compiler(sanitize=args.sanitize)
    if args.sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    guest = guest_object(adapted, out / "guest.o", [*flags, "-O2"])
    fixture = guest_object(
        "tests/pc/libgs_sprite_guest_test.c", out / "fixture.o", [*flags, "-O2"]
    )
    binary = out / ("test-sanitized" if args.sanitize else "test")
    # The library's unrelated SDK services are discarded, rather than stubbed.
    subprocess.run(
        [
            host,
            *flags,
            "-O2",
            guest,
            fixture,
            "src/pc/memory.c",
            "src/pc/guest/translated_runtime.c",
            "src/pc/guest/state_io.c",
            "-Wl,-dead_strip",
            "-o",
            str(binary),
        ],
        cwd=ROOT,
        check=True,
        timeout=60,
    )
    subprocess.run([str(binary)], cwd=ROOT, check=True, timeout=30)


if __name__ == "__main__":
    main()
