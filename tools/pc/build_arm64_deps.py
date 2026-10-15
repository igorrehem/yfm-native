#!/usr/bin/env python3
"""Build pinned macOS ARM64 libraries and tools under repository tmp/."""
import argparse
from macos_deps import ensure

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=int, default=8)
    print(f'Native static dependencies: {ensure(jobs=parser.parse_args().jobs)}')
