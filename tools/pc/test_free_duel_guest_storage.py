#!/usr/bin/env python3
"""Check actual Free Duel cursor and sparkle functions against guest storage."""

import argparse
from pathlib import Path

from guest_build import maps
from guest_test_ir import read_guest_source, run_translated_fixture, select_functions
from translate_guest_ir import translate

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sanitize", action="store_true")
    a = p.parse_args()
    out = ROOT / "tmp/free-duel-guest-storage"
    out.mkdir(parents=True, exist_ok=True)
    raw = read_guest_source(ROOT / "src/overlays/free_duel/screen_runtime.c", out)
    pins = maps()
    ir = out / "cursor.ll"
    ir.write_text(
        translate(
            select_functions(
                raw,
                {
                    "FreeDuel_GetSparkleSlot",
                    "FreeDuel_UpdateSparkle",
                    "FreeDuel_UpdateScrollbar",
                },
            ),
            {**pins["SLUS_014.11"], **pins["free_duel"]},
        )
    )
    run_translated_fixture(
        [ir], ROOT / "tests/pc/free_duel_guest_storage_test.c", out, sanitize=a.sanitize
    )


if __name__ == "__main__":
    main()
