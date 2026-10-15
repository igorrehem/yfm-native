#!/usr/bin/env python3
"""Test the real LIBGS packet sorter with an ILP32 C compiler (no disc)."""
import os
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    out = ROOT / "tmp/pc/libgs-priority-test"
    out.mkdir(parents=True, exist_ok=True)
    binary = out / "test"
    subprocess.run([
        *shlex.split(os.environ.get("CC", "cc")), "-m32", "-std=gnu11", "-O2",
        "-DMEMORIES_PC", "-Isrc", "-ffunction-sections", "-fdata-sections",
        "-fno-builtin", "-fno-pie", "-no-pie", "-Wl,--gc-sections",
        "tests/pc/libgs_priority_test.c", "src/pc/sdk/libgs.c", "-o", str(binary),
    ], cwd=ROOT, check=True)
    subprocess.run([str(binary)], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
