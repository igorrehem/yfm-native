#!/usr/bin/env python3
"""Replay the actual duel card-text stream commands with adjacent pointers."""

import argparse
from pathlib import Path

from guest_test_ir import read_guest_source, run_translated_fixture, select_functions
from translate_guest_ir import address_map, translate

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sanitize", action="store_true")
    a = p.parse_args()
    out = ROOT / "tmp/duel-text-guest-storage"
    out.mkdir(parents=True, exist_ok=True)
    raw = read_guest_source(ROOT / "src/game/duel_effect_command.c", out)
    ir = out / "text.ll"
    ir.write_text(
        translate(
            select_functions(raw, {"func_80037DA4", "func_800384E4"}),
            address_map(ROOT / "config/pc/guest_addresses.txt"),
        )
    )
    run_translated_fixture(
        [ir], ROOT / "tests/pc/duel_text_guest_storage_test.c", out, sanitize=a.sanitize
    )


if __name__ == "__main__":
    main()
