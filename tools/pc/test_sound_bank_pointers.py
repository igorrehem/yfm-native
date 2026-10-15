#!/usr/bin/env python3
"""Replay actual sound bank table reads with the campaign failure sentinels."""

import argparse
from pathlib import Path

from guest_test_ir import read_guest_source, run_translated_fixture, select_functions
from translate_guest_ir import address_map, translate

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sanitize", action="store_true")
    a = p.parse_args()
    out = ROOT / "tmp/sound-bank-pointers"
    out.mkdir(parents=True, exist_ok=True)
    raw = read_guest_source(ROOT / "src/game/sound_output_state.c", out)
    ir = out / "commands.ll"
    ir.write_text(
        translate(
            select_functions(raw, {"func_80045208", "func_80045334"}),
            address_map(ROOT / "config/pc/guest_addresses.txt"),
        )
    )
    run_translated_fixture(
        [ir], ROOT / "tests/pc/sound_bank_pointer_test.c", out, sanitize=a.sanitize
    )


if __name__ == "__main__":
    main()
