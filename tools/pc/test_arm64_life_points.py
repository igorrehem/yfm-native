#!/usr/bin/env python3
"""Exercise a user-supplied life-points mod through real controller input."""

import argparse
import json
import os
import shutil
from pathlib import Path

from gameplay_inputs import inputs
from gameplay_test_support import ROOT, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mod", type=Path, required=True)
    parser.add_argument(
        "--binary", type=Path, default=ROOT / "tmp/pc/macos/memories-arm64"
    )
    parser.add_argument(
        "--case",
        choices=(
            "campaign",
            "campaign-excluded",
            "free-duel",
            "free-duel-excluded",
            "sound-off",
            "damage-timing",
            "restore",
        ),
        default="campaign",
    )
    args = parser.parse_args()
    folder = ROOT / f"tmp/arm64-life-points-tests/{args.case}-{os.getpid()}"
    (folder / "mods").mkdir(parents=True)
    shutil.copytree(args.mod, folder / "mods/life-points")
    starter = folder / "mods/starter"
    starter.mkdir()
    (starter / "mod.json").write_text(
        json.dumps(
            {
                "id": "lp-test-starter",
                "name": "LP test starter",
                "enabled": True,
                "starter": {"name": "LP sound fixture", "347": 40},
            }
        )
    )
    settings = {
        "MEMORIES_TRACE": "mods",
        "MEMORIES_MOD_LIFE_POINTS_PLAYER": "6500",
        "MEMORIES_MOD_LIFE_POINTS_CPU": "9000",
    }
    sequence = inputs(magic=True)
    free = args.case.startswith("free-duel")
    excluded = args.case.endswith("excluded")
    if excluded:
        settings["MEMORIES_MOD_LIFE_POINTS_WHERE"] = "1" if free else "2"
    if args.case == "sound-off":
        settings["MEMORIES_MOD_LIFE_POINTS_SOUND"] = "0"
    if args.case == "damage-timing":
        settings["MEMORIES_MOD_LIFE_POINTS_TIMING"] = "1"
    if args.case == "restore":
        settings["MEMORIES_SAVE_STATE"] = f"8200:{folder / 'duel.state'}"
    if free:
        settings["MEMORIES_MODE_AT"] = "1000:6"
        events = [(f, "0040") for f in range(7600, 8050, 50)]
        events += [(f, "0020") for f in (8100, 8150, 8200, 8250)]
        events += [
            (8500, "4000"),
            (8900, "2000"),
            (9400, "4000"),
            (9800, "4000"),
            (10400, "4000"),
        ]
        events += [(f + 6, "0000") for f, _ in list(events)]
        sequence = (
            inputs().split(",8000:")[0]
            + ","
            + ",".join(f"{f}:{b}" for f, b in sorted(events))
        )
    text = run(
        folder,
        ROOT / "game/YGOFM Vanilla (Base).bin",
        sequence,
        11500,
        args.case,
        settings,
        binary=args.binary.resolve(),
    )
    assert "life-points: loaded life-points.dylib" in text
    assert "life-points: 1 sounds replaced" in text
    assert not any(
        bad in text
        for bad in (
            "refused to start",
            "cannot load ARM64",
            "fatal signal",
            "unimplemented game routine",
        )
    )
    lp = "8000/8000" if excluded else "6500/9000"
    assert f"LP={lp}" in text, f"missing starting LP {lp}"
    if not free:
        final = "8000/7000" if excluded else "6500/8000"
        assert f"LP={final}" in text, f"damage did not occur: {folder}"
        sounds = [
            line
            for line in text.splitlines()
            if "life-points: the counter's sound" in line
        ]
        assert len(sounds) == (0 if args.case == "sound-off" else 1), sounds
        assert (
            "sfx 0x7A00 plays (replaced by life-points)" in text
            or args.case == "sound-off"
        )
    if args.case == "restore":
        assert "ARM64 state saved:" in text
        settings.pop("MEMORIES_SAVE_STATE")
        settings["MEMORIES_LOAD_STATE"] = str(folder / "duel.state")
        remaining = ",".join(
            f"{int(part.split(':')[0]) - 8200 + 30}:{part.split(':')[1]}"
            for part in sequence.split(",")
            if int(part.split(":")[0]) > 8200
        )
        restored = run(
            folder,
            ROOT / "game/YGOFM Vanilla (Base).bin",
            remaining,
            11500 - 8200 + 30,
            "restored",
            settings,
            binary=args.binary.resolve(),
        )
        assert "ARM64 state loading:" in restored and "LP=6500/8000" in restored
        assert "life-points: the counter's sound" in restored
        assert (folder / "restore.ppm").read_bytes() == (
            folder / "restored.ppm"
        ).read_bytes()
    print(
        f"{args.case}: loaded ARM64 mod, LP, scope and counter sound passed; {folder}",
        flush=True,
    )


if __name__ == "__main__":
    main()
