#!/usr/bin/env python3
"""Execute the real SDK descriptor reader reproducing the frame-38 pointer."""

import argparse
from pathlib import Path

from guest_test_ir import read_guest_source, run_translated_fixture, select_functions
from translate_guest_ir import address_map, translate

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    raw = ROOT / "src/pc/sdk/libgpu.c"
    out = ROOT / "tmp/gsdrawot-guest-storage"
    out.mkdir(parents=True, exist_ok=True)
    selected = select_functions(read_guest_source(raw, out), {"GsDrawOt"})
    out = ROOT / "tmp/gsdrawot-guest-storage"
    out.mkdir(parents=True, exist_ok=True)
    ir = out / "GsDrawOt.ll"
    ir.write_text(
        translate(selected, address_map(ROOT / "config/pc/guest_addresses.txt"))
    )
    run_translated_fixture(
        [ir],
        ROOT / "tests/pc/gsdrawot_guest_storage_test.c",
        out,
        sanitize=args.sanitize,
    )


if __name__ == "__main__":
    main()
