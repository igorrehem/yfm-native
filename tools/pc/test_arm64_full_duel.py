#!/usr/bin/env python3
"""Run the upstream adaptive Simon duel in an isolated English/French process.

By default, uses the upstream replay session's controlled eight-card deck.
With --save, follows normal menus and plays the copied save's unmodified deck.
With --animated, that path also runs 3D attacks; --restore --window exercises
live renderer caches after loading a hand state in a fresh process.
Optional texture/code mods and a visible window reproduce distributed-app issues.
This exercises a complete duel; it does not compare English VRAM goldens
against French text. No retail inputs or user saves are changed.
"""

import argparse
import importlib.util
import os
import shutil
from pathlib import Path
from yfm_control import FIELD_CURSOR, MONSTER_RECORDS, TARGET_CURSOR, Game

ROOT = Path(__file__).resolve().parents[2]


def enter_normal_duel(game):
    game.step(2000)
    game.press("start", after=240)
    game.press("down", after=30)
    game.press("cross", after=120)
    game.press("cross", after=240)
    assert game.u8(0x80184594) == 5, "save load did not return to the game menu"
    game.press("down", after=30)
    game.press("cross", after=600)
    assert game.mode() == 6, "normal menu did not reach Free Duel"
    game.shot("free-duel.png")
    game.press("cross", after=120)  # dismiss SELECT OPPONENT
    game.press("right", after=120)  # Simon, next to Build Deck
    game.press("cross", after=120)
    game.duel_ready()
    game.shot("hand.png")
    print(f"Normal Free Duel hand ready: {game.out}", flush=True)


# DuelScene_UpdateFieldActions uses this byte's low nibble: 3 navigates the
# player's field, 4 moves the camera, and 6 accepts the attack target. Wait
# for the actual transition: cursor movement alone is ambiguous for a direct
# attack or while the camera is still moving.
FIELD_ACTION_STATE = 0x8009B174


def attack_normal_field(game, session, *, animated):
    # The retail field handler rejects attacks on the opening turn and while
    # Swords of Revealing Light is active (DuelSideState + 0x19).
    if game.u16("D_8009B16C") & 0x1000 or game.peek("D_800E9FF0", 0x20)[0x19]:
        return
    for column in range(5):
        if session.over(game) or game.turn() != 0:
            return
        records = dict(zip(MONSTER_RECORDS, game.duel()[0]["monsters"]))
        record = game.peek("D_800907D8", 20)[10 + column]
        monster = records.get(record)
        if not monster or monster["used_this_turn"] or monster["defense_position"]:
            continue
        game.wait_until(
            lambda g: g.u8(FIELD_ACTION_STATE) & 15 == 3,
            1200,
            what="field navigation before attack",
        )
        for _ in range(4):
            row = game.u8(FIELD_CURSOR + 1)
            if row == 2:
                break
            game.press("down" if row < 2 else "up", hold=4, after=16)
        game._cursor_to(FIELD_CURSOR, column, "attacker")
        game.press_until(
            lambda g: g.u8(FIELD_ACTION_STATE) & 15 == 6,
            "cross",
            every=120,
            timeout=1200,
            what="attack target selection",
        )
        target = next((i for i, card in enumerate(game.field()[1]) if card), None)
        if target is not None:
            game._cursor_to(TARGET_CURSOR, target, "attack target")
        game.press_until(
            lambda g: g.mode() != 3 or g.phase() != 5,
            "square" if animated and target is not None else "cross",
            every=40,
            timeout=1200,
            what="battle commitment",
        )
        session.settle(game)


def finish_normal_duel(game, session, *, animated=False):
    for turn in range(40):
        if session.over(game):
            break
        game.wait_turn(("hand",))
        if session.over(game):
            break
        print(f"Turn {turn + 1}: frame={game.frame}", flush=True)
        slot = next((i for i, card in enumerate(session.hand_ids(game)) if card), None)
        assert slot is not None, "no playable card in hand"
        game.play_card(slot, face_up=True)
        if not session.over(game) and game.turn() == 0:
            try:
                attack_normal_field(game, session, animated=animated)
            except (RuntimeError, TimeoutError, AssertionError) as error:
                capture = game.shot(f"turn-{turn + 1}-failed.png")
                raise RuntimeError(
                    f"turn {turn + 1}: {error}; inspect {game.out / 'game.log'} "
                    f"and {capture}"
                ) from error
        if not session.over(game):
            game.end_turn()
    assert session.over(game), "duel did not finish within 40 turns"
    game.press_until(
        lambda g: g.phase() == 13, "cross", every=40, timeout=6000, what="result pages"
    )
    game.step(200)
    game.shot("result.png")
    game.press_until(
        lambda g: g.mode() != 3,
        "cross",
        every=40,
        timeout=6000,
        what="results and rewards",
    )
    game.step(240)
    game.shot("return.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--binary", type=Path, default=ROOT / "tmp/pc/macos/memories-arm64"
    )
    parser.add_argument(
        "--disc", type=Path, default=ROOT / "game/YGOFM Vanilla (Base).bin"
    )
    parser.add_argument("--language", type=int, choices=(0, 2), default=0)
    parser.add_argument(
        "--save",
        type=Path,
        help="copy this save and enter Free Duel through normal menus",
    )
    parser.add_argument("--texture-mod", type=Path)
    parser.add_argument("--code-mod", type=Path)
    parser.add_argument(
        "--restore",
        action="store_true",
        help="also restore the normal duel hand in a new process",
    )
    parser.add_argument(
        "--window", action="store_true", help="use a visible 4x HD window"
    )
    parser.add_argument(
        "--animated",
        action="store_true",
        help="use 3D attacks with the normal-save path",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/pc/full-duel")
    args = parser.parse_args()
    if args.restore and not args.save:
        parser.error("--restore requires --save for the normal-menu path")
    binary, disc = args.binary.resolve(), args.disc.resolve()
    if not binary.is_file() or not disc.is_file():
        parser.error("The executable and privately owned disc must exist")
    folder = args.output.resolve() / f"{args.language}-{os.getpid()}"
    mods = folder / "mods"
    mods.mkdir(parents=True, exist_ok=True)
    for name, source in [("assets-hd", args.texture_mod), ("code-mod", args.code_mod)]:
        if source:
            if not (source / "mod.json").is_file():
                parser.error(f"{name} must contain mod.json")
            if name == "assets-hd":
                (mods / name).symlink_to(source.resolve(), target_is_directory=True)
            else:
                shutil.copytree(source.resolve(), mods / name)
    if args.save:
        saves = folder / "user/saves"
        saves.mkdir(parents=True)
        shutil.copyfile(args.save, saves / "slot01.sav")
    spec = importlib.util.spec_from_file_location(
        "full_duel_session", ROOT / "tests/pc/replays/full-duel/session.py"
    )
    session = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(session)
    env = {
        "MEMORIES_DISC": str(disc),
        "MEMORIES_LANGUAGE": str(args.language),
        "MEMORIES_SPEED": "-1",
        "MEMORIES_PAUSE_ON_FOCUS_LOSS": "0",
    }
    if args.window:
        env.update(
            MEMORIES_INTERNAL_SCALE="4",
            MEMORIES_HD_TEXT="1",
            MEMORIES_WINDOW_SHOT="4500",
        )
    with Game(
        binary, out=folder, mods_dir=mods, headless=not args.window, env=env
    ) as game:
        if args.save:
            enter_normal_duel(game)
            if args.restore:
                snapshot = game.duel()
                game.save("hand.state")
            else:
                finish_normal_duel(game, session, animated=args.animated)
        else:
            session.run(game, folder)
        if not args.restore:
            assert game.mode() == 6, (
                f"Expected Free Duel after rewards, got mode {game.mode()}"
            )
    if args.restore:
        with Game(
            binary,
            out=folder / "restored",
            mods_dir=mods,
            headless=not args.window,
            env={**env, "MEMORIES_LOAD_STATE": str(folder / "hand.state")},
        ) as restored:
            restored.step(60)
            assert restored.mode() == 3 and restored.phase() == 4, (
                "hand state did not resume"
            )
            assert restored.duel() == snapshot, "restored hand/field/life points differ"
            restored.shot("hand.png")
            finish_normal_duel(restored, session, animated=args.animated)
            assert restored.mode() == 6, "restored duel did not return to Free Duel"
        print(
            f"Fresh-process hand state and continued duel passed: {folder}", flush=True
        )
    if args.save:
        assert (
            folder / "user/saves/slot01.sav"
        ).read_bytes() == args.save.read_bytes(), "copied save changed"
    if args.window:
        shots = list((folder / "user/screenshots").glob("*.bmp"))
        shots += list((folder / "restored/user/screenshots").glob("*.bmp"))
        assert shots, "no presented window capture"
    print(
        f"Full Simon duel language={args.language}, normal_menus={bool(args.save)}: "
        f"duel, results/rewards and Free Duel return passed; {folder}"
    )


if __name__ == "__main__":
    main()
