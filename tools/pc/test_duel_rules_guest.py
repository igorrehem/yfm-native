#!/usr/bin/env python3
"""Run real translated ritual matching and attack-trap selection."""

import argparse
from pathlib import Path

from guest_test_ir import read_guest_source, run_translated_fixture, select_functions
from translate_guest_ir import address_map, translate

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sanitize", action="store_true")
    a = p.parse_args()
    out = ROOT / "tmp/duel-rules-guest"
    out.mkdir(parents=True, exist_ok=True)
    units = []
    for source, names in [
        (
            "duel_check_ritual",
            {
                "Duel_CheckRitual", "disc_recipe", "printed_attack", "printed_defense", "meets",
                "specificity", "remember_field", "field_objects", "fill_out", "candidate_id",
                "better", "search", "extended_match",
            },
        ),
        (
            "duel_trap_resolution",
            {"Duel_SelectAttackTrap", "select_custom_attack_trap", "resolve_replacement_attack_trap"},
        ),
        ("duel_calc_card_stats", {"Duel_CalcCardStats"}),
    ]:
        raw = read_guest_source(ROOT / f"src/game/{source}.c", out)
        ir = out / (source + ".ll")
        ir.write_text(
            translate(
                select_functions(raw, names),
                address_map(ROOT / "config/pc/guest_addresses.txt"),
            )
        )
        units.append(str(ir))
    run_translated_fixture(
        units, ROOT / "tests/pc/duel_rules_guest_test.c", out, sanitize=a.sanitize
    )


if __name__ == "__main__":
    main()
