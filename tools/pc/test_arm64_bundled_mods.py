#!/usr/bin/env python3
"""Retail-disc checks for packaged Hand Camera and Yamyi's Back prompt."""

import argparse
import json
import shutil
from pathlib import Path

from yfm_control import Game

ROOT = Path(__file__).resolve().parents[2]


def camera(args):
    results = {}
    for enabled in (0, 1):
        folder = args.output / f"camera-{enabled}"
        with Game(args.binary, out=folder, mods_dir=args.mods,
                  headless=not args.window,
                  settings={"mod.hand-camera": enabled, "mod.3d-monsters": 1,
                            "mod.yamyi-mods": 0, "mod.ai-hard-mode": 0,
                            "mod.drop-missing-cards": 0}, env=args.env) as game:
            game.wait_until(lambda g: g.resident("main_menu"), 3000)
            game.goto("duel", opponent=1, deck="425,425,337,330,339,1,1,1")
            game.duel_ready()
            assert game.phase() == 4, "hand must be open"
            angle = lambda: game.u16(0x800F284A)
            distance = lambda: game.u16(0x800F2848)
            start = [angle(), distance()]
            game.shot("before.png")
            game.press("r1", hold=12, after=1)
            turned = angle()
            assert (turned != start[0]) == bool(enabled), "R1 activation differs"
            game.press("l1", hold=12, after=1)
            assert (angle() != turned) == bool(enabled), "L1 activation differs"
            game.press("r3", hold=12, after=1)
            farther = distance()
            assert (farther > start[1]) == bool(enabled), "R3 zoom differs"
            game.press("l3", hold=12, after=1)
            assert (distance() < farther) == bool(enabled), "L3 zoom differs"
            game.shot("after.png")
            results[str(enabled)] = {"start": start, "turned": turned, "farther": farther}
        log = (folder / "game.log").read_text()
        if enabled:
            assert "hand-camera: loaded" in log, "packaged camera mod did not load"
    return results


def back_prompt(args):
    folder = args.output / "back-prompt"
    saves = folder / "user/saves"
    saves.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.save, saves / "slot01.sav")
    with Game(args.binary, out=folder, mods_dir=args.mods,
              headless=not args.window,
              settings={"mod.yamyi-mods": 1, "mod.3d-monsters": 0,
                        "mod.hand-camera": 0, "mod.ai-hard-mode": 0,
                        "mod.drop-missing-cards": 0}, env=args.env) as game:
        # LOAD through the actual title and slot chooser, without a debug jump
        # (debug-launched screens return to the debug menu, not the mode wheel).
        game.wait_until(lambda g: g.resident("main_menu"), 3000)
        game.press_until(lambda g: g.u8("gMain_bMenuID") == 1,
                         ["start", "down"], every=90, timeout=6000)
        game.step(120)
        game.press("cross", after=90)
        game.press_until(lambda g: g.resident("main_menu") and g.u8("gMain_bMenuID") >= 5,
                         "cross", every=60, timeout=6000)
        game.step(120)
        selection = game.u8("gMain_bMenuID")
        assert selection >= 5, "must be on mode-select wheel"
        base = game.shot("wheel.png").read_bytes()
        for answer in ("circle", "no", "yes"):
            game.press("circle", after=30)
            prompt = game.shot(f"prompt-{answer}.png").read_bytes()
            assert prompt != base, "Back prompt did not draw"
            assert game.resident("main_menu") and game.u8("gMain_bMenuID") == selection
            if answer == "yes":
                game.press("left", after=12)
            game.press("circle" if answer == "circle" else "cross", after=120)
            if answer == "yes":
                game.wait_until(lambda g: g.u8("gMain_bMenuID") == 1, 1000)
                game.shot("title.png")
            else:
                assert game.resident("main_menu") and game.u8("gMain_bMenuID") == selection
                assert game.shot(f"closed-{answer}.png").read_bytes() == base
    log = (folder / "game.log").read_text()
    assert "yamyi-mods: loaded" in log, "packaged Yamyi mod did not load"
    assert "menu-back-confirm: closed (circle)" in log
    assert log.count("menu-back-confirm: closed (cross)") == 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--mods", type=Path, required=True)
    parser.add_argument("--disc", type=Path, required=True)
    parser.add_argument("--save", type=Path, required=True, help="retail .sav copied into an isolated profile")
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/bundled-mods-regression")
    parser.add_argument("--window", action="store_true")
    args = parser.parse_args()
    args.env = {"MEMORIES_DISC": str(args.disc.resolve()), "MEMORIES_TRACE": "mods",
                "MEMORIES_SPEED": "-1", "MEMORIES_PAUSE_ON_FOCUS_LOSS": "0"}
    if args.window:
        args.env.update(MEMORIES_INTERNAL_SCALE="4", MEMORIES_HD_TEXT="1", MEMORIES_NO_AUDIO="1")
    results = camera(args)
    back_prompt(args)
    (args.output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(f"Hand Camera and Back prompt passed; {args.output}")


if __name__ == "__main__":
    main()
