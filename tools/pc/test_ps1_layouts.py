#!/usr/bin/env python3
"""Compare shared PS1 records on console, Linux, Windows, Android and macOS ABIs.

Only guest headers are included. Host window/settings/save-state structures
deliberately remain native. Compilation errors and missing records fail the
check; no header is silently skipped.
"""

import argparse
import re
import subprocess
from pathlib import Path

from llvm_guest import ROOT, toolchain

HEADERS = (
    "src/ygo_types.h",
    "src/psyq/libgte.h",
    "src/psyq/libgpu.h",
    "src/psyq/libgs.h",
)
from guest_test_compile import PS1_TARGETS as TARGETS


def layouts(compiler, flags):
    result = subprocess.run(
        [
            str(compiler),
            *flags,
            "-ffreestanding",
            "-fms-extensions",
            "-Isrc",
            "-Isrc/psyq",
            "-w",
            "-fsyntax-only",
            "-Xclang",
            "-fdump-record-layouts-complete",
            "-Xclang",
            "-fdump-record-layouts-simple",
            *(argument for header in HEADERS for argument in ("-include", header)),
            "-x",
            "c",
            "-",
        ],
        input="",
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    tags = set()
    for header in HEADERS:
        tags.update(
            re.findall(r"\b(?:struct|union)\s+(\w+)\s*\{", (ROOT / header).read_text())
        )
    found = {}
    for name, layout in re.findall(
        r"Type: ([^\n]+)\n\nLayout: <ASTRecordLayout\n(.*?)>", result.stdout, re.S
    ):
        # Exclude compiler-native records such as __NSConstantString_tag.
        if "(unnamed at " in name:
            if not any(header in name for header in HEADERS):
                continue
        elif name.split()[-1] not in tags:
            continue
        found[name] = layout.strip()
    if not found:
        raise RuntimeError("Clang produced no PS1 record layouts")
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--clang", type=Path, help="explicit compiler; default is pinned LLVM 21.1.8"
    )
    args = parser.parse_args()
    compiler = args.clang or toolchain() / "bin/clang"
    baseline = layouts(compiler, TARGETS["console"])
    failed = []
    for name, flags in TARGETS.items():
        if name == "console":
            continue
        actual = layouts(compiler, flags)
        differences = sorted(
            record
            for record in baseline.keys() | actual.keys()
            if baseline.get(record) != actual.get(record)
        )
        for record in differences:
            failed.append(
                f"{name}: {record}\n  PS1: {baseline.get(record)}\n  host: {actual.get(record)}"
            )
    if failed:
        raise SystemExit("\n".join(failed))
    print(
        f"{len(baseline)} shared PS1 records: sizes, alignments and field offsets match "
        "console/Linux i386/Windows i686+x64/Android ARM64/macOS ARM64"
    )


if __name__ == "__main__":
    main()
