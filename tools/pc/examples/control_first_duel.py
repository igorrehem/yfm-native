#!/usr/bin/env python3
"""The first story duel, driven through the control channel (yfm_control.py).

One game process: boots, starts a new game (Start, NEW GAME, the name "A"),
follows the story to the first duel by the main mode, reads both sides' life
points and the hand as data, plays the first card of the hand, and takes a
picture at each step. No frame numbers: every wait is on what the game holds
(the mode, a module being resident, the name, the hand, the field). Run
twice (the default), the two runs must agree on every number and picture.

    python3 tools/pc/examples/control_first_duel.py [--executable PATH] [--runs N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yfm_control import Game, MODE, OUTPUT  # noqa: E402


def picture(game: Game, name: str, record: dict) -> None:
    """A PNG in the run's folder; the record keeps its pixels' hash."""
    path = game.shot(f"{name}.png")
    record.setdefault("pictures", {})[name] = {"frame": game.frame, "vram": f"{game.hash():016x}",
                                               "png": hashlib.sha256(path.read_bytes()).hexdigest()[:16]}


def cards(row: list) -> list:
    return [card and card["id"] for card in row]


def play(executable: Path | None, out: Path) -> dict:
    record: dict = {}
    with Game(executable, out=out) as game:
        record["build"] = f"{game.info()['build']:08x}"
        drive(game, record)
    return record


def drive(game: Game, record: dict) -> None:
    """From boot to the first card played (tests/pc/replays/first-duel records it)."""
    # The title comes with the main menu's module; Start skips the
    # opening, opens the menu, and Cross takes NEW GAME, its first item.
    game.wait_until(lambda g: g.resident("main_menu"), 3000, what="the title")
    game.press_until(lambda g: g.resident("password"), ["start", "cross"], every=40, what="the name entry")
    # Cross types the letter under the cursor once the screen takes
    # input; Start goes to END, and Cross takes END and then YES.
    game.press_until(lambda g: g.player_name(), "cross", every=20, what="a letter of the name")
    picture(game, "1-name", record)
    game.press("start")
    game.press_until(lambda g: g.mode() == MODE["campaign"], "cross", every=40, what="the story")
    record["story_frame"] = game.frame
    # The story's dialogue and the map, then the duel.
    game.press_until(lambda g: g.mode() == MODE["duel"], "cross", every=40, timeout=20000, what="the duel")
    record["duel_frame"] = game.frame
    picture(game, "2-duel-begins", record)
    # The deck's screen before it (in the main menu's module): Circle
    # leaves it. Then the five cards are dealt.
    game.press_until(lambda g: not g.resident("main_menu"), "circle", every=60, what="the duel field")
    game.wait_until(lambda g: all(g.duel()[0]["hand"]), 3000, every=10, what="the hand")
    game.step(200)   # the cards come up from the deck: the hand is shown and takes input
    sides = game.duel()
    record["opponent"] = game.u8("gDuel_bOpponentID")
    record["lp"] = [side["lp"] for side in sides]
    record["hand"] = cards(sides[0]["hand"])
    record["hand_stats"] = [(card["attack"], card["defense"]) for card in sides[0]["hand"]]
    picture(game, "3-hand", record)
    # The first card: Cross picks it, Cross again puts it down, Cross
    # takes the first zone and Cross the guardian star offered first.
    game.press_until(lambda g: any(g.duel()[0]["monsters"]), "cross", every=46, timeout=1200,
                     what="the card on the field")
    game.step(120)
    sides = game.duel()
    record["after_play"] = {"hand": cards(sides[0]["hand"]), "monsters": cards(sides[0]["monsters"]),
                            "lp": [side["lp"] for side in sides], "frame": game.frame}
    picture(game, "4-played", record)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--executable", type=Path, help="the game (default: yfm_control's)")
    parser.add_argument("--out", type=Path, help="where the runs go (default: a new tmp/pc/control/first-duel-*)")
    parser.add_argument("--runs", type=int, default=2)
    arguments = parser.parse_args()
    if not arguments.out:   # a folder of its own: two at once must not share one
        OUTPUT.mkdir(parents=True, exist_ok=True)
        arguments.out = Path(tempfile.mkdtemp(prefix="first-duel-", dir=OUTPUT))
    records = []
    for run in range(arguments.runs):
        out = arguments.out.resolve() / f"run{run + 1}"
        shutil.rmtree(out, ignore_errors=True)
        record = play(arguments.executable, out)
        (out / "record.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
        print(f"run {run + 1}: story at frame {record['story_frame']}, duel at {record['duel_frame']}, "
              f"pictures and numbers in {out / 'record.json'}")
        records.append(record)
    if any(record != records[0] for record in records[1:]):
        print("first duel: the runs differ", file=sys.stderr)
        return 1
    hand, played = records[0]["hand"], records[0]["after_play"]
    print(f"first duel: {arguments.runs} runs identical; LP {records[0]['lp']}, hand {hand}, "
          f"card {played['monsters'][0]} on the field, hand now {played['hand']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
