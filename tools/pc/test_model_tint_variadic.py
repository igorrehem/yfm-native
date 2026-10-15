#!/usr/bin/env python3
"""Execute the translated tint-mask builder using native variadic arguments."""

import argparse
from pathlib import Path

from guest_test_ir import read_guest_source, run_translated_fixture, select_functions
from translate_guest_ir import translate

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sanitize", action="store_true")
    a = p.parse_args()
    out = ROOT / "tmp/model-tint-variadic"
    out.mkdir(parents=True, exist_ok=True)
    raw = read_guest_source(ROOT / "src/game/func_80058838.c", out)
    ir = translate(
        select_functions(raw, {"Model_QueueTintRequestForParts", "mark_part"}), {}
    )
    (out / "tint.ll").write_text(ir)
    run_translated_fixture(
        [out / "tint.ll"],
        ROOT / "tests/pc/model_tint_variadic_test.c",
        out,
        sanitize=a.sanitize,
    )


if __name__ == "__main__":
    main()
