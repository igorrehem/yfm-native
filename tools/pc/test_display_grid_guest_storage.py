#!/usr/bin/env python3
"""Exercise the real three-word grid writers and readers with neighboring sentinels."""

import argparse
from pathlib import Path

from guest_test_ir import read_guest_source, run_translated_fixture, select_functions
from translate_guest_ir import address_map, translate

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    out = ROOT / "tmp/display-grid-guest-storage"
    out.mkdir(parents=True, exist_ok=True)
    units = []
    for source, names in [
        (
            "display_effect_resource_setup",
            {
                "DisplayEffect_HasResourceEntry",
                "DisplayEffect_BuildResourceObjects",
                "func_8003A440",
            },
        ),
        ("display_effect_lifecycle", {"func_80039F90"}),
    ]:
        raw = read_guest_source(ROOT / f"src/game/{source}.c", out)
        target = out / (source + ".ll")
        target.write_text(
            translate(
                select_functions(raw, names),
                address_map(ROOT / "config/pc/guest_addresses.txt"),
            )
        )
        units.append(str(target))
    run_translated_fixture(
        units,
        ROOT / "tests/pc/display_grid_guest_storage_test.c",
        out,
        sanitize=args.sanitize,
    )


if __name__ == "__main__":
    main()
