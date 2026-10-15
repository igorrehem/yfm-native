#!/usr/bin/env python3
"""Live test of a mod's lock on Game > Card drops (built game and user-supplied disc).

A mod's "limits": {"card_drops": n} makes every won duel deal n cards,
whatever the player set (notes/card-drops.md, "A mod that sets it"). This
wins test_card_drops.py's duel with mods in a test user directory and
counts the cards awarded on leaving RESULTS OF DUEL:

- a mod's 5 over the player's 99, and over MEMORIES_CARD_DROPS=99, deals 5;
- a mod's 99 over the player's 1 deals 99;
- the mod removed, the player's own 99 is dealt again;
- a mod's 0 is noted ("is at least 1; left out") and the player's count dealt;
- of two mods that lock it, the one applied later deals, and the earlier
  one is noted.

A state keeps the mods it was made with, so each case plays the duel's
opening with its own mods. The test also saves the window with Game open
(the locked row greyed and named after the mod, and the same menu without
the mod) as menu-locked.bmp and menu-player.bmp. Everything stays in
tmp/pc/card-drops-mod-smoke (or --out); no player saves are touched.

    python3 tools/pc/test_card_drops_mod.py [--windows | --executable PATH] [--out DIR]
"""
import argparse
import json
from pathlib import Path
import shutil

import test_card_drops as drops

OUT = drops.ROOT / "tmp/pc/card-drops-mod-smoke"
MENU_AT = 700          # the title: Game opened by a click, the window saved
GAME_MENU = (200, 13)  # the bar's Game at the menu's scale 1 (menu.c layout_bar)
CARD_DROPS_ROW = (280, 157)  # its Card drops row, open


def mods(folder, manifests):
    """`folder`'s test user directory gets these mods (id -> "limits"
    "card_drops" value); the settings lines that apply them."""
    root = folder / "user" / "mods"
    shutil.rmtree(root, ignore_errors=True)
    lines = ""
    for mod_id, value in manifests.items():
        (root / mod_id).mkdir(parents=True)
        manifest = {"id": mod_id, "name": f"Lock {mod_id}", "enabled": True, "limits": {"card_drops": value}}
        (root / mod_id / "mod.json").write_text(json.dumps(manifest))
        lines += f"mod.{mod_id}=1\n"
    return lines


def ending(executable, label, manifests):
    """The duel just before its win, played with these mods."""
    folder = drops.OUT / label / "hand"
    folder.mkdir(parents=True, exist_ok=True)
    more = mods(folder, manifests)
    opening = json.loads((drops.ROOT / "tests/pc/smoke/duel-hand-camera.json").read_text())["input"]
    hand = drops.run(executable, label + "/hand", drops.HAND, opening, settings_more=more)
    data, memory = drops.chunks(hand)
    for address in (drops.OPPONENT_LP, drops.OPPONENT_SHOWN_LP):
        drops.struct.pack_into("<h", data, memory + address - 0x80000000, 0)
    path = drops.OUT / label / "ending.state"
    path.write_bytes(data)
    return path


def won(executable, label, player, manifests, env=None):
    """The cards a won duel awards with the player's setting at `player` and
    these mods applied, and the run's log."""
    folder = drops.OUT / label
    folder.mkdir(parents=True, exist_ok=True)
    start = ending(executable, label, manifests)
    more = mods(folder, manifests)
    before = drops.chest(start)
    done = drops.run(executable, label, drops.RESULTS + 900,
                     drops.WIN + "," + drops.presses(drops.RESULTS + 20, [drops.CROSS]), start, drops=player,
                     settings_more=more, env_more=env)
    log = (folder / "run.log").read_text(errors="replace")
    assert "state load failed" not in log, f"{label}: the duel's state did not load"
    gained = [a - b for a, b in zip(drops.chest(done), before)]
    first = drops.peek(done, drops.record(done) + drops.DROPPED_CARD, "h")
    assert drops.peek(done, drops.RECENT, "H") == first, f"{label}: SPOILS' card should be the last awarded"
    return sum(gained), log


def menu_shot(executable, label, manifests):
    """The window with Game open at the title, as a player sees it, and the
    player's saved Card drops after Left on its row (the pointer resting
    there): 98 from 99, or 99 still while a mod locks it."""
    folder = drops.OUT / label
    folder.mkdir(parents=True, exist_ok=True)
    more = mods(folder, manifests)
    x, y = GAME_MENU
    row_x, row_y = CARD_DROPS_ROW
    drops.run(executable, label, MENU_AT + 40, drops=99, settings_more=more + "menu_scale=1\n",
              env_more={"MEMORIES_SDL_SCRIPT": f"{MENU_AT}:click:{x}:{y},{MENU_AT + 5}:move:{row_x}:{row_y},"
                                               f"{MENU_AT + 10}:key:left,{MENU_AT + 20}:shot",
                        "MEMORIES_WINDOW_SHOT": "0"})
    shots = sorted(folder.glob("*.bmp"))
    assert shots, f"{label}: no window shot"
    saved = [line for line in (folder / "settings.txt").read_text().splitlines() if line.startswith("card_drops=")]
    return shots[-1], saved


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--windows", action="store_true", help="test the Windows build under Wine")
    parser.add_argument("--executable", type=Path, help="the game to test (default: the build for this host)")
    parser.add_argument("--out", type=Path, help=f"where the runs are kept (default: {OUT})")
    parser.add_argument("--menus", action="store_true", help="only the two menu pictures")
    arguments = parser.parse_args()
    executable = drops.WINDOWS_EXECUTABLE if arguments.windows else drops.EXECUTABLE
    if arguments.executable:
        executable = arguments.executable.resolve()
    drops.OUT = (arguments.out or OUT).resolve()

    locked, saved = menu_shot(executable, "menu-locked", {"lock-five": 5})
    assert saved == ["card_drops=99"], f"Left on the locked row should keep the player's 99: {saved}"
    player, saved = menu_shot(executable, "menu-player", {})
    assert saved == ["card_drops=98"], f"Left on the player's row should make 99 98: {saved}"
    shutil.copy(locked, drops.OUT / "menu-locked.bmp")
    shutil.copy(player, drops.OUT / "menu-player.bmp")
    assert locked.read_bytes() != player.read_bytes(), "the locked menu should look other than the player's"
    log = (drops.OUT / "menu-locked" / "run.log").read_text(errors="replace")
    assert "state load failed" not in log and "mod lock-five:" not in log, "the lock should load without a note"
    if arguments.menus:
        print(f"card drops mod lock: menus in {drops.OUT}")
        return

    count, _ = won(executable, "lock-5-player-99", 99, {"lock-five": 5})
    assert count == 5, f"a mod's 5 over the player's 99 should deal 5, not {count}"
    count, _ = won(executable, "lock-5-env-99", 1, {"lock-five": 5}, {"MEMORIES_CARD_DROPS": "99"})
    assert count == 5, f"a mod's 5 over MEMORIES_CARD_DROPS=99 should deal 5, not {count}"
    count, _ = won(executable, "lock-99-player-1", 1, {"lock-all": 99})
    assert count == 99, f"a mod's 99 over the player's 1 should deal 99, not {count}"
    count, _ = won(executable, "removed-player-99", 99, {})
    assert count == 99, f"without the mod the player's 99 should be dealt, not {count}"
    count, log = won(executable, "bad-0-player-99", 99, {"lock-zero": 0})
    assert count == 99, f"a mod's 0 is left out: the player's 99, not {count}"
    assert 'mod lock-zero: limits: "card_drops" is at least 1; left out' in log, "the bad value should be noted"
    count, log = won(executable, "two-mods", 99, {"lock-a": 5, "lock-b": 7})
    assert count == 7, f"of two mods the later one (lock-b, 7) should deal, not {count}"
    assert 'mod lock-a: limits: "card_drops" 5 is not used: lock-b, applied later, locks it at 7' in log, \
        "the earlier mod should be noted"
    print(f"card drops mod lock: 5 over 99 (and over MEMORIES_CARD_DROPS), 99 over 1, the player's 99 back, "
          f"a bad value and two mods passed; menus in {drops.OUT}")


if __name__ == "__main__":
    main()
