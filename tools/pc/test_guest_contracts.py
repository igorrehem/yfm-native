#!/usr/bin/env python3
"""Run ROM-free regressions against freshly compiled guest source functions."""

import argparse
import subprocess
import sys

from llvm_guest import ROOT

CASES = (
    "ai_vm_guest_callbacks",
    "campaign_map_guest_storage",
    "display_grid_guest_storage",
    "duel_card_guest_storage",
    "duel_ritual_guest_storage",
    "duel_rules_guest",
    "duel_text_guest_storage",
    "free_duel_guest_storage",
    "gsdrawot_guest_storage",
    "menu_entry_guest_storage",
    "model_effect_guest_callbacks",
    "model_rows_guest_storage",
    "model_tint_variadic",
    "sound_bank_pointers",
    "sound_guest_storage",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    for case in (args.case,) if args.case else CASES:
        print(f"Guest contract: {case}", flush=True)
        subprocess.run(
            [
                sys.executable,
                str(ROOT / f"tools/pc/test_{case}.py"),
                *(["--sanitize"] if args.sanitize else []),
            ],
            cwd=ROOT,
            check=True,
            timeout=180,
        )
    print(f"{1 if args.case else len(CASES)} guest source contracts passed")


if __name__ == "__main__":
    main()
