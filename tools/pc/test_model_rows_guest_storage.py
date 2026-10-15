#!/usr/bin/env python3
"""Run real HMD row/channel readers with adjacent guest-pointer sentinels."""

import argparse
from pathlib import Path

from guest_test_ir import read_guest_source, run_translated_fixture, select_functions
from translate_guest_ir import address_map, translate

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sanitize", action="store_true")
    a = p.parse_args()
    out = ROOT / "tmp/model-rows-guest-storage"
    out.mkdir(parents=True, exist_ok=True)
    raw = read_guest_source(ROOT / "src/game/model_slot_row_tables.c", out)
    ir = out / "rows.ll"
    ir.write_text(
        translate(
            select_functions(raw, {"func_8004D58C", "func_8004D134"}),
            address_map(ROOT / "config/pc/guest_addresses.txt"),
        )
    )
    units = [str(ir)]
    for source, names in [
        ("src/game/model_handler_registry.c", {"Model_ProcessType2Unit"}),
        ("src/pc/sdk/libgs_unit.c", {"GsLinkAnim"}),
    ]:
        unit = out / (Path(source).name + ".ll")
        unit.write_text(
            translate(
                select_functions(read_guest_source(source, out), names),
                address_map(ROOT / "config/pc/guest_addresses.txt"),
            )
        )
        units.append(str(unit))
    run_translated_fixture(
        units,
        ROOT / "tests/pc/model_rows_guest_storage_test.c",
        out,
        sanitize=a.sanitize,
    )


if __name__ == "__main__":
    main()
