#!/usr/bin/env python3
"""Check CoreText font discovery and rendered card-title plates without a game."""

import argparse
from macos_font_checks import run_fonts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    run_fonts(sanitize=args.sanitize)


if __name__ == "__main__":
    main()
