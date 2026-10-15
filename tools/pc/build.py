#!/usr/bin/env python3
"""Common game build entry point for supported PC target descriptors.

Additional arguments are passed to the selected architecture's driver.
The existing Linux/Windows compiler and ABI stay selected by their driver.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from build_config import ROOT, TARGETS


def main():
    default = os.environ.get('MEMORIES_TARGET') or ('windows' if sys.platform == 'win32' else 'macos' if sys.platform == 'darwin' else 'linux')
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--target', choices=TARGETS, default=default)
    parser.add_argument('--build', type=Path, help='Override the target build directory')
    options, forwarded = parser.parse_known_args()
    target = TARGETS[options.target]
    directory = options.build or Path('tmp/pc/game32' if options.target == 'windows' and sys.platform == 'win32'
                                     else target['build'])
    command = [sys.executable, str(Path(__file__).with_name(target['driver']))]
    if options.target != 'macos': command += ['--target', options.target]
    command += ['--build', str(directory), *forwarded]
    return subprocess.run(command, cwd=ROOT).returncode


if __name__ == '__main__':
    raise SystemExit(main())
