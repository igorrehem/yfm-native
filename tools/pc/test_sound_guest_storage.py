#!/usr/bin/env python3
"""Execute actual translated sound commands with neighbor-word sentinels."""

import argparse
from pathlib import Path

from translate_guest_ir import address_map, translate

ROOT = Path(__file__).resolve().parents[2]


from guest_test_ir import read_guest_source, run_translated_fixture, select_functions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    out = ROOT / "tmp/sound-guest-storage"
    out.mkdir(parents=True, exist_ok=True)
    units = []
    for source, functions in [
        ("src/game/sd_arm_busy_callback.c", {"SD_ArmBusyCallback"}),
        ("src/game/sound_init.c", {"SD_ResetMusicTrackBuffer"}),
        ("src/game/func_8004ADE8.c", {"func_8004ADE8"}),
    ]:
        original = source
        selected = select_functions(read_guest_source(original, out), functions)
        adapted = translate(
            selected, address_map(ROOT / "config/pc/guest_addresses.txt")
        )
        target = out / (Path(source).name + ".ll")
        target.write_text(adapted)
        units.append(str(target))
    run_translated_fixture(
        units, ROOT / "tests/pc/sound_guest_storage_test.c", out, sanitize=args.sanitize
    )


if __name__ == "__main__":
    main()
