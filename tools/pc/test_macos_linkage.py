#!/usr/bin/env python3
"""Verify real Mach-O architecture, linkage and installed font rendering."""

import argparse
import re
import subprocess
from pathlib import Path

from build_config import MACOS_MINIMUM
from llvm_guest import compiler, toolchain
from macos_deps import INSTALL, ROOT, ensure
from macos_font_checks import run_fonts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--binary", type=Path, default=ROOT / "tmp/pc/macos/memories-arm64"
    )
    args = parser.parse_args()
    ensure()
    for name in ("libSDL3.a", "libfreetype.a", "libpng16.a", "libz.a", "libzstd.a"):
        archive = INSTALL / "lib" / name
        arch = subprocess.check_output(
            ["lipo", "-archs", str(archive)], text=True
        ).strip()
        assert arch == "arm64", f"{archive}: wrong architectures: {arch}"
        commands = subprocess.check_output(["otool", "-l", str(archive)], text=True)
        minimums = re.findall(r"\bminos ([0-9.]+)", commands)
        assert minimums, f"{archive}: missing deployment target in archive objects"
        baseline = tuple(map(int, MACOS_MINIMUM.split("."))) + (0,)
        for minimum in minimums:
            version = tuple(map(int, minimum.split(".")))
            version += (0,) * (3 - len(version))
            assert version <= baseline, (
                f"{archive}: object requires macOS {minimum}, baseline is {MACOS_MINIMUM}"
            )
    for binary in (args.binary.resolve(), compiler()):
        commands = subprocess.check_output(["otool", "-l", str(binary)], text=True)
        rpaths = re.findall(
            r"cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset", commands
        )
        lines = subprocess.check_output(
            ["otool", "-L", str(binary)], text=True
        ).splitlines()[1:]
        for line in lines:
            dependency = line.strip().split(" (")[0]
            if dependency.startswith(("/System/Library/", "/usr/lib/")):
                continue
            if dependency.startswith("@loader_path/"):
                resolved = (
                    binary.parent / dependency.removeprefix("@loader_path/")
                ).resolve()
                assert (
                    resolved.is_relative_to(toolchain().resolve())
                    and resolved.is_file()
                ), dependency
                continue
            if dependency.startswith("@rpath/"):
                candidates = [
                    Path(path.replace("@loader_path", str(binary.parent)))
                    / dependency.removeprefix("@rpath/")
                    for path in rpaths
                ]
                assert any(
                    path.resolve().is_relative_to(toolchain().resolve())
                    and path.is_file()
                    for path in candidates
                ), dependency
                continue
            raise AssertionError(
                f"{binary}: unexpected runtime dependency {dependency}"
            )
    run_fonts()
    print(
        "macOS static library architectures/deployment targets, system/local runtime linkage and fonts passed"
    )


if __name__ == "__main__":
    main()
