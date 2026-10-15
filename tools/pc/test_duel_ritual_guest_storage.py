#!/usr/bin/env python3
"""Exercise the ritual's actual card/data publication branch."""

import argparse
from pathlib import Path

from guest_test_ir import read_guest_source, run_translated_fixture, select_functions
from llvm_guest import inspect
from translate_guest_ir import address_map, translate

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sanitize", action="store_true")
    a = p.parse_args()
    out = ROOT / "tmp/duel-ritual-guest-storage"
    out.mkdir(parents=True, exist_ok=True)
    raw = read_guest_source(ROOT / "src/game/duel_ritual_effect.c", out)
    selected = select_functions(raw, {"DuelEffect_ApplyRitual"})
    ir = out / "ritual.ll"
    ir.write_text(
        translate(selected, address_map(ROOT / "config/pc/guest_addresses.txt"))
    )
    # Every dependency outside the publication branch must stay unexecuted.
    names = set(inspect(selected)["declarations"])
    stubs = out / "unused.c"
    stubs.write_text(
        "#include <stdlib.h>\nint rand(void) { abort(); }\n"
        + "\n".join(
            f"void {name}(void) {{ abort(); }}"
            for name in sorted(names)
            if name not in {"DuelEffect_MarkInitialized", "StoreImage", "rand"}
            and not name.startswith("llvm.")
        )
    )
    run_translated_fixture(
        [ir],
        ROOT / "tests/pc/duel_ritual_guest_storage_test.c",
        out,
        sanitize=a.sanitize,
        extra_sources=[stubs],
    )


if __name__ == "__main__":
    main()
