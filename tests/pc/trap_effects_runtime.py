"""Disc-backed editor manifest -> native duel -> CPU trap checks.

python3 tests/pc/trap_effects_runtime.py --out tmp/pc/trap-runtime
Each scenario gives the CPU a fixed deck so its real AI must set the edited
trap. The player then supplies the trigger using normal controller input.
"""
import argparse
import json
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/pc"))
from fm_editor import disc, gamedata, manifest
from fm_editor.model import Project
from yfm_control import Game, FIELD_CURSOR, TARGET_CURSOR


def attack_direct(game, column=0):
    # After playing magic the first Cross can open the card panel. Confirm
    # the target cursor is active before committing the attack.
    for _ in range(4):
        row = game.u8(FIELD_CURSOR + 1)
        if row == 2:
            break
        game.press("down" if row < 2 else "up", hold=4, after=16)
    game._cursor_to(FIELD_CURSOR, column, "field")
    for _ in range(4):
        game.press("cross", hold=4, after=80)
        aim = game.u8(TARGET_CURSOR)
        game.press("left" if aim else "right", hold=4, after=16)
        if game.u8(TARGET_CURSOR) != aim:
            break
        game._cursor_to(FIELD_CURSOR, column, "field")
    else:
        raise AssertionError("attack target cursor did not open")
    game.press_until(lambda g: g.phase() != 5, "cross", every=40, timeout=1200, what="attack commitment")
    game._settle()


def run(executable, out, limit=0, start=1, hard_mode=False):
    retail = gamedata.load_game(disc.find_game([ROOT / "game"]))
    project = Project(retail)
    project.info.id = "trap-test"
    cases = [(effect, threshold, "attack") for effect in range(681, 687) for threshold in (999, 1000, 1001)]
    cases += [(effect, None, "special") for effect in range(687, 691)]
    cases += [(681, threshold, "defend") for threshold in (999, 1000)]
    cases += [(683, 1000, "attack"), (681, 1000, "attack")]
    # Original effect cards can change type without changing the behaviors.
    for cid in range(681, 691):
        project.cards[cid] = project.cards[cid].copy(type=0, attack=100, defense=100, attribute=0)
        project.card_extra[cid] = {"model": 5}
    decks = {}
    ids = []
    for opponent, (effect, threshold, kind) in enumerate(cases, 1):
        cid = 690 if opponent == 25 else 1 if opponent == 26 else project.add_card(3, f"trap-{opponent}")
        ids.append(cid)
        project.cards[cid] = project.cards[cid].copy(type=21, attack=0, defense=0, level=0,
                                                    star1=0, star2=0, attribute=7)
        extra = project.added[cid].extra if cid in project.added else project.card_extra.setdefault(cid, {})
        extra["effect"] = effect
        if threshold is not None:
            project.set_trap_threshold(cid, threshold)
        key = project.identity(cid) if cid in project.added else str(cid)
        decks[gamedata.DUELIST_NAMES[opponent]] = {"fixed": True, "5" if kind == "defend" else key: 40}
    built = manifest.build(project)
    built["decks"] = decks
    mod = out / "mods/trap-test"
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "mod.json").write_text(json.dumps(built), encoding="utf-8")
    if hard_mode:
        link = out / "mods/ai-hard-mode"
        if not link.exists():
            link.symlink_to((executable.parent / "mods/ai-hard-mode").resolve(), target_is_directory=True)
    with Game(executable=executable, out=out / "game", mods_dir=out / "mods",
              settings={"mod.trap-test": 1, "mod.ai-hard-mode": int(hard_mode),
                        "mod.ai-hard-mode.trace": int(hard_mode), "mod.3d-monsters": 0, "mod.hand-camera": 0},
              env={"MEMORIES_TRACE_MODS": "1"}) as game:
        for opponent, ((effect, threshold, kind), cid) in enumerate(zip(cases, ids), 1):
            if opponent < start:
                continue
            if limit and opponent > limit:
                break
            trigger = 339 if effect == 688 else 303 if effect == 689 else 343
            if kind == "defend":
                game.goto("duel", opponent=opponent, deck=[cid, 5, 4, 6, 7, 8, 9, 10])
                game.duel_ready(before_deal=lambda g: g.arrange_deck(0, [cid, 5, 4, 6, 7]))
                game.play_card(0)
                game.end_turn()
                after = game.duel()
                fired = threshold >= 1000
                assert bool(after[0]["spells"][0]) != fired, after
                assert bool(after[1]["monsters"][0]) != fired, after
                assert after[0]["lp"] == (8000 if fired else 7000), after
                print(f"CPU attacked player trap {cid}; threshold {threshold}: passed", flush=True)
                continue
            game.goto("duel", opponent=opponent, deck=[5, trigger, 4, 6, 7, 8, 9, 10])
            game.duel_ready(before_deal=lambda g: g.arrange_deck(0, [5, trigger, 4, 6, 7]))
            game.play_card(0, face_up=True)
            game.end_turn()
            traps = [c for c in game.duel()[1]["spells"] if c]
            assert len(traps) == 1 and traps[0]["id"] == cid and traps[0]["face_down"], game.duel()
            if effect == 688:
                game.poke(game.address("D_800E9FF0") + 0x12, struct.pack("<HH", 5000, 5000))
            before = game.duel()
            rank_before = game.u8(game.address("D_800E9FF0") + 0x20 + 6)
            slot = next(i for i, c in enumerate(before[0]["hand"]) if c and c["id"] == trigger)
            if effect == 689:
                game._hand_to(slot)
                game.press("cross", hold=4, after=60)
                game.press("cross", hold=4, after=80)
                game._cursor_to(FIELD_CURSOR, 0, "equip target")
                game.press_until(lambda g: g.phase() != 4, "cross", every=40, timeout=1200,
                                 what="equip on the occupied monster slot")
                game._settle()
            else:
                game.play_card(slot)
            if kind == "attack" or effect == 690:
                attack_direct(game)
            game.step(120)
            after = game.duel()
            if kind == "attack":
                fired = threshold >= 1000
                assert bool(after[1]["spells"][0]) != fired, after
                assert bool(after[0]["monsters"][0]) != fired, after
                assert after[1]["lp"] == before[1]["lp"] - 50 - (0 if fired else 1000), after
            else:
                fired = True
                assert not any(after[1]["spells"]), after
                if effect == 687:
                    assert after[0]["lp"] == before[0]["lp"] - 50 and after[1]["lp"] == before[1]["lp"], after
                elif effect == 688:
                    assert after[0]["lp"] == 4500, after
                elif effect == 689:
                    modifier = struct.unpack("<h", game.peek(game.address("D_801A7AD8") + 5 * 28 + 0x12, 2))[0]
                    assert after[0]["monsters"][0]["attack"] + modifier == 500, (after, modifier)
                elif effect == 690:
                    assert after[0]["monsters"][0], after
            assert game.u8(game.address("D_800E9FF0") + 0x20 + 6) == rank_before + int(fired)
            print(f"CPU set card {cid}; effect {effect}, threshold {threshold}: passed", flush=True)
        if hard_mode:
            assert "ai-hard-mode: opponent=" in game.log_path.read_text(errors="replace"), "hard-mode planner did not run"
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=ROOT / "tmp/pc/game32/memories-pc")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--hard-mode", action="store_true")
    args = parser.parse_args()
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        raise SystemExit(run(args.executable, args.out, args.limit, args.start, args.hard_mode))
    with tempfile.TemporaryDirectory(prefix="fm-traps-") as folder:
        raise SystemExit(run(args.executable, Path(folder), args.limit, args.start, args.hard_mode))
