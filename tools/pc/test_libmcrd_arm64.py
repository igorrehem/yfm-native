#!/usr/bin/env python3
"""Verify native PS1 memory-card ABI and real isolated filesystem round trips."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    output = ROOT / 'tmp/libmcrd-arm64'
    output.mkdir(parents=True, exist_ok=True)
    flags = ['-O2', '-std=gnu11', '-D_DARWIN_C_SOURCE', '-D_LANGUAGE_C', '-DMEMORIES_PC',
             '-fms-extensions', '-w', '-I' + str(ROOT / 'src'),
             '-idirafter', str(ROOT / 'src/psyq'),
             '-include', str(ROOT / 'src/types.h'),
             '-include', str(ROOT / 'src/psyq/kernel.h')]
    if args.sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = output / ('card-test-sanitized' if args.sanitize else 'card-test')
    sources = ['tests/pc/libmcrd_arm64_test.c', 'src/pc/sdk/libmcrd.c', 'src/pc/platform/paths.c']
    subprocess.run(['xcrun', 'clang', *flags, *(str(ROOT / s) for s in sources), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    main()
