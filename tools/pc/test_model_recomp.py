#!/usr/bin/env python3
"""The translated MODEL variant modules against the interpreter
(MEMORIES_MODEL_MODULES=interpreter), on the control client. Each scenario is
a duel against Simon Muran with a deck of one monster: it is played face up,
and next turn it attacks with the 3D presentation (Square), which loads both
monsters' variant modules and runs their choreography. The two sides must
agree on every frame hash and every model-module call, the translated side
must have run translated code, and each scenario must have run a module.

    python3 tools/pc/test_model_recomp.py [--executable PATH] [card ids...]
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from yfm_control import Game, OUTPUT, TARGET_CURSOR, FIELD_CURSOR, ControlError  # noqa: E402

OUT = OUTPUT / "model-recomp"
SIMON = 1
# Blue-eyes White Dragon, Mystical Elf, Shadow Specter, Tyhone, Kuriboh, Battle
# Warrior, Arlownay, Emperor of the Land and Sea, Dragon Seeker, Key Mace #2.
MONSTERS = [1, 2, 9, 13, 58, 100, 180, 400, 500, 600]
CALL = re.compile(r"frame (\d+) vb \d+ model\] (variant .*)")
VERDICT = re.compile(r"model\] variant module (\d+) \(slot ([AB])\): (.*)")


def attack_3d(game, column, target):
    """yfm_control's attack, committed with Square: the 3D battle."""
    game.wait_turn()
    for _ in range(4):
        row = game.u8(FIELD_CURSOR + 1)
        if row == 2:
            break
        game.press("down" if row < 2 else "up", hold=4, after=16)
    game._cursor_to(FIELD_CURSOR, column, "field")
    game.press("cross", hold=4, after=40)
    if target is not None:
        game._cursor_to(TARGET_CURSOR, target, "target")
    game.press("square", hold=4, after=30)
    game._settle()


def battle(game):
    game.play_card(0, face_up=True)
    game.end_turn()
    game.play_card(0, face_up=True)
    target = next((column for column, card in enumerate(game.field()[1]) if card), None)
    attack_3d(game, 0, target)


def side(executable, name, env, monsters):
    out = OUT / name
    shutil.rmtree(out, ignore_errors=True)
    (out / "mods").mkdir(parents=True)
    env = {**env, "MEMORIES_FRAME_HASHES": str(out / "hashes.txt"), "MEMORIES_TRACE": "model",
           "MEMORIES_LOG": str(out / "log.txt")}
    spans = {}
    with Game(executable, out=out, settings={"mod.3d-monsters": 0, "mod.hand-camera": 0}, mods_dir=out / "mods",
              env=env) as game:
        for card in monsters:
            first, error = game.frame, None
            try:
                game.goto("duel", opponent=SIMON, deck=str(card))
                game.duel_ready()
                battle(game)
                game.step(240)
            except (TimeoutError, RuntimeError, StopIteration, ValueError, ControlError) as failure:
                error = f"{type(failure).__name__}: {failure}"
            spans[card] = (first, game.frame, game.shot(f"{card}.png"), error)
    return out, spans


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("cards", nargs="*", type=int)
    arguments = parser.parse_args()
    global OUT
    if arguments.out:
        OUT = arguments.out.resolve()
    else:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        OUT = Path(tempfile.mkdtemp(prefix="model-recomp-", dir=OUTPUT))
    monsters = arguments.cards or MONSTERS
    with ThreadPoolExecutor(2) as pool:
        translated = pool.submit(side, arguments.executable, "translated", {}, monsters)
        interpreted = pool.submit(side, arguments.executable, "interpreter",
                                  {"MEMORIES_MODEL_MODULES": "interpreter"}, monsters)
        (t_out, t_spans), (i_out, i_spans) = translated.result(), interpreted.result()
    hashes = [dict(line.split() for line in (out / "hashes.txt").read_text().splitlines()) for out in (t_out, i_out)]
    logs = [(out / "log.txt").read_text(errors="replace").splitlines() for out in (t_out, i_out)]
    calls = [[(int(m.group(1)), m.group(2)) for m in map(CALL.search, log) if m] for log in logs]
    verdicts = [m.groups() for m in map(VERDICT.search, logs[0]) if m]
    translated_modules = {(module, slot) for module, slot, verdict in verdicts if verdict == "translated"}
    failed = 0
    for card in monsters:
        (first, last, _, error), other = t_spans[card], i_spans[card]
        frames = [str(frame) for frame in range(first, last + 1)]
        differing = next((frame for frame in frames if hashes[0].get(frame) != hashes[1].get(frame)), None)
        mine = [call for call in calls[0] if first <= call[0] <= last]
        theirs = [call for call in calls[1] if first <= call[0] <= last]
        ok = not error and not other[3] and (first, last) == other[:2] and differing is None and mine == theirs \
            and mine
        failed += not ok
        print(f"model recomp: card {card}: {'ok' if ok else 'FAILED'}: frames {first}-{last}, {len(mine)} module calls"
              + (f"; {error or other[3]}" if error or other[3] else "")
              + (f"; first differing frame {differing}" if differing else "")
              + ("; the calls differ" if mine != theirs else "") + ("; no module ran" if not mine else ""))
    if not translated_modules:
        failed += 1
        print("model recomp: FAILED: no module ran translated")
    print(f"model recomp: {len(monsters) - failed} of {len(monsters)} agree; {len(translated_modules)} translated "
          f"module loads; pictures in {t_out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
