#!/usr/bin/env python3
"""Verify real AI VM terminators compare guest callback tokens correctly."""

import argparse
from pathlib import Path

from guest_test_ir import read_guest_source, run_translated_fixture, select_functions
from translate_guest_ir import address_map, translate

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sanitize", action="store_true")
    a = p.parse_args()
    out = ROOT / "tmp/ai-vm-guest-callbacks"
    out.mkdir(parents=True, exist_ok=True)
    units = []
    for source, names in [
        ("ai_script_vm", {"AiScript_Init", "AiScript_Run", "AiScript_ReadByte"}),
        (
            "ai_script_end",
            {"AiScript_EndHand", "AiScript_EndField", "AiScript_PlayFieldCard"},
        ),
    ]:
        raw = read_guest_source(ROOT / f"src/game/{source}.c", out)
        raw = raw.replace("@bzero(", "@test_guest_bzero(")
        ir = out / (source + ".ll")
        ir.write_text(
            translate(
                select_functions(raw, names),
                address_map(ROOT / "config/pc/guest_addresses.txt"),
            )
        )
        units.append(str(ir))
    run_translated_fixture(
        units, ROOT / "tests/pc/ai_vm_guest_callbacks_test.c", out, sanitize=a.sanitize
    )


if __name__ == "__main__":
    main()
