#!/usr/bin/env python3
"""Headless native ARM64 gameplay checks using a user-owned retail disc.

Exercises real name entry, campaign, deck menu and card animations. It uses
controller inputs, never writes gameplay RAM, and keeps all saves/art in tmp.
Build with tools/pc/build_arm64.py first. No window/audio cadence is measured.
"""

import argparse
import json
import os
import re
from pathlib import Path

from gameplay_inputs import (
    animated_battle_inputs,
    deck_editor_inputs,
    deck_sorted_add_inputs,
    inputs,
    retail_ritual_inputs,
    ritual_inputs,
)
from gameplay_test_support import clean_environment, run_game

ROOT = Path(__file__).resolve().parents[2]
CASES = (
    "fusion-failure",
    "fusion",
    "equip",
    "magic",
    "victory",
    "free-duel",
    "deck-editor",
    "deck-editor-free-duel",
    "deck-editor-add-sorted",
    "animated-battle",
    "trap",
    "trap-threshold",
    "ritual",
    "ritual-failure",
    "ritual-retail",
)


def check_retail_ritual_recipe(disc):
    from fm_editor.disc import DiscImage
    from fm_editor.gamedata import (
        RITUAL_LENGTH,
        RITUAL_OFFSET,
        TERRAIN_BASE,
        TERRAIN_STRIDE,
        decode_rituals,
    )

    with DiscImage(disc) as image:
        lba, _ = image.find("DATA/WA_MRG.MRG")
        for terrain in range(7):
            offset = TERRAIN_BASE + terrain * TERRAIN_STRIDE + RITUAL_OFFSET
            recipe = decode_rituals(image.read(lba + offset // 2048, RITUAL_LENGTH))[
                670
            ]
            assert recipe == (27, 38, 58, 364), (
                f"unexpected retail ritual recipe: {recipe}"
            )


def run(case, disc, binary, output, language=0, state_frame=None):
    folder = output / case
    mods = folder / "mods"
    mods.mkdir(parents=True, exist_ok=True)
    if case in (
        "equip",
        "magic",
        "victory",
        "animated-battle",
        "trap",
        "trap-threshold",
        "ritual",
        "ritual-failure",
        "ritual-retail",
    ):
        fixture = mods / "starter"
        fixture.mkdir(exist_ok=True)
        manifest = {
            "id": "arm64-mechanics",
            "name": "ARM64 mechanics fixture",
            "version": "1",
            "enabled": True,
            "starter": (
                {"name": "Equip fixture", "75": 20, "657": 20}
                if case == "equip"
                else {"name": "Damage fixture", "347": 40}
            ),
        }
        if case == "animated-battle":
            manifest["starter"] = {"name": "Battle fixture", "75": 20, "347": 20}
        if case.startswith("trap"):
            manifest["starter"] = {
                "name": "Trap fixture",
                "686" if case == "trap" else "681": 40,
            }
        if case == "trap-threshold":
            manifest["decks"] = {"all": {"fixed": True, "75": 40}}
        if case.startswith("ritual"):
            manifest["starter"] = {"name": "Ritual fixture", "1": 30, "670": 10}
            manifest["rituals"] = [{"card": 670, "tributes": [1, 1, 1], "result": 364}]
            manifest["decks"] = {"all": {"fixed": True, "75": 40}}
        if case == "ritual-retail":
            check_retail_ritual_recipe(disc)
            del manifest["rituals"]
            manifest["starter"] = {
                "name": "Retail ritual fixture",
                "27": 10,
                "38": 10,
                "58": 10,
                "670": 10,
            }
            manifest["decks"] = {"all": {"fixed": True, "338": 40}}
        if case == "victory":
            manifest["limits"] = {"life_points": {"opponent": 1000}}
        (fixture / "mod.json").write_text(json.dumps(manifest))
    env = clean_environment()
    env.update(
        MEMORIES_HEADLESS="1",
        MEMORIES_NO_AUDIO="1",
        MEMORIES_NO_GAMEPAD="1",
        MEMORIES_NO_UPDATE_CHECK="1",
        MEMORIES_SPEED="-1",
        MEMORIES_TRACE_GAMEPLAY="1",
        MEMORIES_LANGUAGE=str(language),
        MEMORIES_DISC=str(disc),
        MEMORIES_USER_DIR=str(folder / "user"),
        MEMORIES_MODS_DIR=str(mods),
        MEMORIES_INPUT=inputs(case == "fusion", case in ("magic", "victory")),
        MEMORIES_DUMP_FRAME="11500",
        MEMORIES_DUMP_PATH=str(folder / "end.ppm"),
    )
    if case == "animated-battle":
        env["MEMORIES_INPUT"] = animated_battle_inputs()
        env["MEMORIES_DUMP_FRAME"] = "32000"
    if case.startswith("trap"):
        # Stop confirming after the face-down trap is placed; selecting it
        # again consumes it. End the turn and let the CPU attack normally.
        env["MEMORIES_INPUT"] = (
            ",".join(
                part
                for part in inputs(magic=True).split(",")
                if int(part.split(":")[0]) < 9600
            )
            + ",11000:0008,11006:0000"
        )
        env["MEMORIES_DUMP_FRAME"] = "20000"
    if case.startswith("ritual"):
        env["MEMORIES_INPUT"] = (
            retail_ritual_inputs()
            if case == "ritual-retail"
            else ritual_inputs(case == "ritual-failure")
        )
        env["MEMORIES_DUMP_FRAME"] = "16000" if case == "ritual-failure" else "29000"
    if case.startswith("deck-editor"):
        env["MEMORIES_INPUT"] = deck_editor_inputs()
        env["MEMORIES_DUMP_FRAME"] = "16800"
        if case == "deck-editor-add-sorted":
            env["MEMORIES_INPUT"] = deck_sorted_add_inputs()
            env["MEMORIES_DUMP_FRAME"] = "10000"
        if case == "deck-editor-free-duel":
            env["MEMORIES_MODE_AT"] = "1000:6"
            env["MEMORIES_INPUT"] = ",".join(
                part
                for part in env["MEMORIES_INPUT"].split(",")
                if int(part.split(":")[0]) < 15900
            )
            env["MEMORIES_DUMP_FRAME"] = "15600"
    if case == "free-duel":
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
        env["MEMORIES_INPUT"] = (
            inputs().split(",8000:")[0]
            + ","
            + ",".join(f"{f}:{b}" for f, b in sorted(events))
        )
        env["MEMORIES_MODE_AT"] = "1000:6"
    log = folder / "run.log"
    if state_frame is not None:
        assert 30 < state_frame < int(env["MEMORIES_DUMP_FRAME"])
        env["MEMORIES_SAVE_STATE"] = f"{state_frame}:{folder / 'replay.state'}"
    text = run_game(binary, env, log)
    if state_frame is not None:
        replay = env.copy()
        replay.pop("MEMORIES_SAVE_STATE")
        replay["MEMORIES_LOAD_STATE"] = str(folder / "replay.state")
        replay["MEMORIES_INPUT"] = ",".join(
            f"{int(part.split(':')[0]) - state_frame + 30}:{part.split(':')[1]}"
            for part in env["MEMORIES_INPUT"].split(",")
            if int(part.split(":")[0]) > state_frame
        )
        replay["MEMORIES_DUMP_FRAME"] = str(
            int(env["MEMORIES_DUMP_FRAME"]) - state_frame + 30
        )
        replay["MEMORIES_DUMP_PATH"] = str(folder / "replay.ppm")
        run_game(binary, replay, folder / "replay.log")
        assert "ARM64 state loading:" in (folder / "replay.log").read_text()
        assert (folder / "end.ppm").read_bytes() == (
            folder / "replay.ppm"
        ).read_bytes(), f"{case}: state replay pixels differ"
        print(f"{case}: fresh-process save-state replay pixels match", flush=True)
    assert (folder / "end.ppm").is_file(), f"{case}: no completed frame capture; {log}"
    for failure in (
        "cannot run;",
        "using the native stand-in",
        "unimplemented game routine",
    ):
        assert failure not in text, (
            f"{case}: gameplay used a fallback: {failure}; {log}"
        )
    check = (
        check_ritual
        if case.startswith("ritual")
        else check_trap
        if case.startswith("trap")
        else check_animated_battle
        if case == "animated-battle"
        else check_sorted_deck
        if case == "deck-editor-add-sorted"
        else check_deck_editor
        if case.startswith("deck-editor")
        else check_victory
        if case == "victory"
        else check_card_mechanics
    )
    try:
        check(case, text, log)
    except (AssertionError, ValueError) as error:
        raise AssertionError(f"{case}: {error}; inspect {log}") from error


def check_ritual(case, text, log):
    ending = text[
        text.index(
            "gameplay frame=" + ("15960" if case == "ritual-failure" else "28920")
        ) :
    ]
    assert "duel phase=8005 action=83 side=0" in ending, (
        f"{case}: no return to field; {log}"
    )
    if case == "ritual-failure":
        assert "duel field= 5:1/3000/2500/0/0\n" in ending
        assert "hand=670,0,1,1,1" in ending and ":364/" not in text
    elif case == "ritual-retail":
        field_lines = [
            line for line in text.splitlines() if line.startswith("duel field=")
        ]
        assert any(
            set(re.findall(r" \d+:(\d+)/", line)) == {"27", "38", "58"}
            for line in field_lines
        ), f"retail tributes not established; {log}"
        assert "duel field= 5:364/3000/2500/0/0\n" in ending
        assert "hand=0,670,38,58,670" in ending and "LP=8000/8000" in ending
    else:
        assert any(
            len(re.findall(r" \d+:1/", line)) == 3
            for line in text.splitlines()
            if line.startswith("duel field=")
        ), f"three distinct tributes not established; {log}"
        assert "duel field= 7:364/3000/2500/0/0\n" in ending, (
            f"ritual result/tribute removal incorrect; {log}"
        )
        assert "hand=0,670,1,1,670" in ending
    print(
        f"{case}: ritual conditions, card consumption and return to field passed; {log}",
        flush=True,
    )
    return


def check_trap(case, text, log):
    ending = text[text.index("gameplay frame=19920") :]
    expected = (
        ("traps=1/0", "LP=8000/8000", "duel backrow=\n", "duel opponent=\n")
        if case == "trap"
        else (
            "traps=0/0",
            "LP=7200/8000",
            "duel backrow= 10:681/",
            "duel opponent= 20:75/",
        )
    )
    for evidence in ("duel phase=8004", "turns=1/1", *expected):
        assert evidence in ending, f"{case}: missing {evidence!r}; {log}"
    assert f"duel backrow= 10:{686 if case == 'trap' else 681}/" in text
    print(
        f"{case}: trap placement, attack threshold, counters, LP and return to hand passed; {log}",
        flush=True,
    )
    return


def check_animated_battle(case, text, log):
    start = text.index("mode=c1")
    ending = text[start:]
    for evidence in (
        "mode=c3 sub=81",
        "LP=7700/6500",
        "turns=1/1",
        "duel phase=8005 action=83 side=0",
        "5:75/800/600/0/0",
    ):
        assert evidence in ending, f"{case}: missing {evidence!r} after 3D entry; {log}"
    print(f"{case}: 3D animation, damage and return to field passed; {log}", flush=True)
    return


def check_sorted_deck(case, text, log):
    removed = text.index("deck=39 chest=1")
    assert "pane=1 sort=0 mode=1 first=0 target=0 cursor=0 card=24" in text[:removed]
    assert "pane=0 sort=0 mode=1 first=16 target=16 cursor=7 card=24" in text[removed:]
    assert "deck=40 chest=0 effect=0" in text[removed:], (
        f"ID-sorted deck not restored: {log}"
    )
    print(
        f"{case}: add lowest card to sorted deck without temporary-pointer crash passed; {log}",
        flush=True,
    )
    return


def check_deck_editor(case, text, log):
    for pane in (0, 1):
        for choice in range(7):
            assert f"decklist pane={pane} sort={choice} " in text, (
                f"missing pane {pane} sort {choice}: {log}"
            )
    ending = (
        ("gameplay frame=15480 mode=c6",)
        if case == "deck-editor-free-duel"
        else (
            "gameplay frame=16680 mode=c3 sub=81",
            "duel phase=8004 action=84 side=0 LP=8000/8000",
        )
    )
    for evidence in (
        "deck=39 chest=1",
        "effect=130",
        "first=16 target=16 cursor=7 card=24",
        "first=32 target=32",
        *ending,
    ):
        assert evidence in text, f"{case}: missing {evidence!r}; {log}"
    assert "deck=40 chest=0 effect=0" in text[text.index("deck=39 chest=1") :], (
        f"deck not restored: {log}"
    )
    print(
        f"{case}: all sorts, panes, paging, card viewer, remove/add and exit passed; {log}",
        flush=True,
    )
    return


def check_victory(case, text, log):
    for evidence in (
        "LP=8000/0",
        "duel phase=800d",
        "mode=c2 sub=02 scene=96",
        "inventory chest=1 starchips=5",
    ):
        assert evidence in text, f"{case}: missing {evidence!r}; {log}"
    print(f"victory: results, reward and campaign dialogue passed; {log}", flush=True)
    return


def check_card_mechanics(case, text, log):
    assert "gameplay frame=11400 mode=c3 sub=81" in text, (
        f"{case}: did not remain in duel; {log}"
    )
    if case == "free-duel":
        assert "duel phase=8008 action=83 side=0 LP=8000/8000" in text, (
            f"{case}: no guardian-star selection; {log}"
        )
        print(
            f"free-duel: grid movement, deck menu, Duel Master K and guardian-star selection passed; {log}",
            flush=True,
        )
        return
    life = "8000/7000" if case == "magic" else "8000/8000"
    assert f"duel phase=8005 action=83 side=0 LP={life}" in text, (
        f"{case}: no return to player field with expected LP; {log}"
    )
    expected = {
        "fusion-failure": ("fusions=0/0 equips=0/0", "5:549/700/500/0/0"),
        "fusion": ("fusions=1/0 equips=0/0", "5:487/1800/1400/0/0"),
        "equip": ("fusions=0/0 equips=1/0", "5:75/800/600/1000/0"),
        "magic": ("magic=1/0", "hand=0,347,347,347,347"),
    }[case]
    for evidence in expected:
        assert evidence in text, f"{case}: missing {evidence!r}; {log}"
    print(
        f"{case}: card animations, counters, field card and statistics passed; {log}",
        flush=True,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--disc", type=Path, default=ROOT / "game/YGOFM Vanilla (Base).bin")
    p.add_argument("--case", choices=CASES)
    p.add_argument("--binary", type=Path, default=ROOT / "tmp/pc/macos/memories-arm64")
    p.add_argument(
        "--output", type=Path, default=ROOT / f"tmp/arm64-gameplay/run-{os.getpid()}"
    )
    p.add_argument("--language", type=int, choices=range(6), default=0)
    p.add_argument(
        "--state-frame",
        type=int,
        help="Save here and replay the remaining inputs in a fresh process",
    )
    args = p.parse_args()
    disc = args.disc.resolve()
    if not disc.is_file():
        p.error("a user-owned retail disc is required")
    binary = args.binary.resolve()
    if not binary.is_file():
        p.error("build the requested executable first")
    for case in [args.case] if args.case else CASES:
        run(case, disc, binary, args.output.resolve(), args.language, args.state_frame)


if __name__ == "__main__":
    main()
