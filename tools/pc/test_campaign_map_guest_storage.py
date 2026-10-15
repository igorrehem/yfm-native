#!/usr/bin/env python3
"""Exercise actual map cleanup using its retail four-word pointer table."""

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
    out = ROOT / "tmp/campaign-map-guest-storage"
    out.mkdir(parents=True, exist_ok=True)
    raw = read_guest_source(ROOT / "src/overlays/overworld/set_location.c", out)
    pins = maps()
    ir = out / "map.ll"
    ir.write_text(
        translate(
            select_functions(raw, {"CampaignMap_ClearLocationObjects"}),
            {**pins["SLUS_014.11"], **pins["overworld"]},
        )
    )
    run_translated_fixture(
        [ir],
        ROOT / "tests/pc/campaign_map_guest_storage_test.c",
        out,
        sanitize=a.sanitize,
    )


if __name__ == "__main__":
    main()
