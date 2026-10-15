"""Disc-backed checks through the native game's real card-use path.

Run from the repo root after tools/pc/build_game32.py:
    python3 tests/pc/magic_effects_runtime.py
Uses isolated mods, settings and saves; requires the user's game files.
"""
import argparse
import json
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/pc"))
from yfm_control import Game
from fm_editor import disc, gamedata


def run(executable, out):
    mods = out / "mods"
    mod = mods / "magic-test"
    mod.mkdir(parents=True, exist_ok=True)
    # The source slots are changed too. Explicit effect references must
    # still select the original retail behavior, without following a chain.
    entries = [
        {"replace": 1, "type": "Magic", "effect": 343},
        {"replace": 2, "type": "Magic", "effect": 339},
        {"copy": 3, "id": "forest", "type": "Magic", "effect": 330},
        {"replace": 686, "type": "Magic", "effect": 337},
        {"replace": 337, "type": "Magic", "effect": 343},
    ]
    retail = gamedata.load_game(disc.find_game([ROOT / "game"]))
    magic = [cid for cid, c in sorted(retail.cards.items()) if c.type == gamedata.TYPE_MAGIC]
    entries += [{"replace": cid, "type": "Dragon", "model": 5, "name": "Changed source"}
                for cid in magic if cid != 337]
    entries += [{"copy": 3, "id": f"effect-{cid}", "type": "Magic", "effect": cid}
                for cid in magic]
    (mod / "mod.json").write_text(json.dumps({"id": "magic-test", "name": "Magic test", "cards": entries}))
    with Game(executable=executable, out=out / "game", mods_dir=mods,
              settings={"mod.magic-test": 1, "mod.3d-monsters": 0, "mod.hand-camera": 0}) as game:
        cases = [(1, 343, "damage"), (2, 339, "heal"), (723, 330, "terrain"),
                 (686, 337, "destroy"), (337, 343, "damage")]
        cases += [(724 + i, effect, "activation") for i, effect in enumerate(magic)]
        for card, effect, behavior in cases:
            game.goto("duel", opponent=1, deck=[5, card, 4, 6, 7, 8, 9, 10])
            game.duel_ready(before_deal=lambda g: g.arrange_deck(0, [5, card, 4, 6, 7]))
            if behavior == "destroy":
                game.play_card(0, face_up=True)
                game.end_turn()
                assert any(game.field()[1]), "opponent must have a monster for Raigeki"
            # Healing must have room to work; use the normal side-state LP.
            if behavior == "heal":
                game.poke(game.address("D_800E9FF0") + 0x12, struct.pack("<HH", 5000, 5000))
            before = game.duel()
            slot = next(i for i, c in enumerate(before[0]["hand"]) if c and c["id"] == card)
            # Magic starts face up; the helper's right press would set it.
            game.play_card(slot)
            game.step(120)
            after = game.duel()
            assert game.u16("gDuel_wEffectCardID") == effect, (card, effect, game.u16("gDuel_wEffectCardID"))
            assert game.u16("gDuel_wCardEffectFlags") == 0, "effect did not finish"
            if behavior == "damage":
                assert after[1]["lp"] == before[1]["lp"] - 50, after
            elif behavior == "heal":
                assert after[0]["lp"] == 5500, after
            elif behavior == "terrain":
                assert game.u8("gDuel_bTerrain") == 1
            elif behavior == "destroy":
                assert not any(game.field()[1]), game.field()
            print(f"card {card}: retail effect {effect} ({behavior}) passed", flush=True)
    print(f"All {len(magic)} retail magic effects activated and completed on converted copies.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=ROOT / "tmp/pc/game32/memories-pc")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        raise SystemExit(run(args.executable, args.out))
    with tempfile.TemporaryDirectory(prefix="fm-magic-") as folder:
        raise SystemExit(run(args.executable, Path(folder)))
