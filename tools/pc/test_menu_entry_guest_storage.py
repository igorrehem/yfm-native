#!/usr/bin/env python3
"""Run the real overlay transition with the adjacent pointers from frame506."""

import argparse
from pathlib import Path

from guest_build import maps
from guest_test_ir import read_guest_source, run_translated_fixture, select_functions
from translate_guest_ir import translate

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    raw = ROOT / "src/overlays/main_menu/frontend_background.c"
    out = ROOT / "tmp/menu-entry-guest-storage"
    out.mkdir(parents=True, exist_ok=True)
    selected = select_functions(
        read_guest_source(raw, out), {"MainMenu_StartFrontendEntryTransition"}
    )
    pin_maps = maps()
    pins = {**pin_maps["SLUS_014.11"], **pin_maps["main_menu"]}
    out = ROOT / "tmp/menu-entry-guest-storage"
    out.mkdir(parents=True, exist_ok=True)
    ir = out / "menu-entry.ll"
    ir.write_text(translate(selected, pins))
    run_translated_fixture(
        [ir],
        ROOT / "tests/pc/menu_entry_guest_storage_test.c",
        out,
        sanitize=args.sanitize,
    )


if __name__ == "__main__":
    main()
