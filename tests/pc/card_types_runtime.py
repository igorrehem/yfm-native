"""Save/reopen an FM Editor mod, then play every monster type, equips and rituals.

Requires the player's disc and a built native game. Uses isolated saves/mods:
    python3 tests/pc/card_types_runtime.py --out tmp/pc/card-types-runtime
"""
import argparse
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/pc"))
from fm_editor import disc, fixed_decks, gamedata, manifest
from fm_editor.model import Project
from yfm_control import Game
from trap_effects_runtime import attack_direct


def run(executable, out):
    retail = gamedata.load_game(disc.find_game([ROOT / "game"]))
    project = Project(retail)
    project.info.id = "card-types-test"
    monsters = []
    for kind in range(gamedata.TYPE_MAGIC):
        cid = project.add_card(3, f"type-{kind}")
        project.cards[cid] = project.cards[cid].copy(type=kind, attack=1230, defense=890, star1=0, star2=0)
        monsters.append(cid)
    # The reverse conversion must summon/attack as a monster too.
    project.cards[343] = project.cards[343].copy(type=0, attack=2340, defense=1200, star1=0, star2=0)
    project.card_extra[343] = {"model": 5}
    monsters.append(343)
    equip = project.add_card(3, "equip")
    ritual = project.add_card(3, "ritual")
    for cid, kind, effect in ((equip, gamedata.TYPE_EQUIP, 303), (ritual, gamedata.TYPE_RITUAL, 675)):
        project.cards[cid] = project.cards[cid].copy(type=kind, attack=0, defense=0,
                                                   star1=0, star2=0, level=0, attribute=6)
        project.added[cid].extra["effect"] = effect
        project.cards[effect] = project.cards[effect].copy(type=0, attack=100, defense=100)
        project.card_extra[effect] = {"model": 5}
    project.rituals[ritual] = (5, 5, 5, 1)
    messages = []
    fixed_decks.read_entry(project, gamedata.DUELIST_NAMES[1], {"fixed": True, "687": 40}, messages)
    assert not messages, messages
    mod = out / "mods/card-types-test"
    manifest.save_mod(project, mod)
    reopened, messages = manifest.open_mod(retail, mod)
    assert not messages, messages
    assert manifest.build(reopened) == manifest.build(project), "save/reopen changed the mod"
    with Game(executable=executable, out=out / "game", mods_dir=out / "mods",
              settings={"mod.card-types-test": 1, "mod.3d-monsters": 0, "mod.hand-camera": 0}) as game:
        for cid in monsters:
            card = project.cards[cid]
            game.goto("duel", opponent=1, deck=[cid, 4, 6, 7, 8, 9, 10])
            game.duel_ready(before_deal=lambda g: g.arrange_deck(0, [cid, 4, 6, 7, 8]))
            game.play_card(0, face_up=True)
            monster = game.duel()[0]["monsters"][0]
            assert monster and (monster["id"], monster["attack"], monster["defense"]) == (
                cid, card.attack, card.defense), game.duel()
            # The opening turn forbids attacks; Goblin Fan lets the next
            # turn's direct attack resolve without destroying the monster.
            game.end_turn()
            active = struct.iter_unpack("<hhhHbbbB", game.peek("gDuel_aActiveCards", 112 * 12))
            assert {record[4] for record in active if record[0] == cid} == {card.type}, cid
            slot = next(i for i, c in enumerate(game.duel()[0]["hand"]) if c and c["id"] == 4)
            game.play_card(slot, face_up=True)
            attack_direct(game)
            assert game.duel()[1]["lp"] == 8000 - card.attack, game.duel()
            print(f"card {cid}: {gamedata.TYPE_NAMES[card.type]} summoned and attacked for {card.attack}", flush=True)

        game.goto("duel", opponent=1, deck=[5, equip, 4, 6, 7, 8, 9])
        game.duel_ready(before_deal=lambda g: g.arrange_deck(0, [5, equip, 4, 6, 7]))
        game.fuse([0, 1], face_up=True)
        column = next(i for i, c in enumerate(game.duel()[0]["monsters"]) if c and c["id"] == 5)
        game.end_turn()
        slot = next(i for i, c in enumerate(game.duel()[0]["hand"]) if c and c["id"] == 4)
        game.play_card(slot, face_up=True)
        attack_direct(game, column)
        assert game.duel()[1]["lp"] == 6500, game.duel()
        print("converted equip: +500 applied and used in battle", flush=True)

        game.goto("duel", opponent=1, deck=[5, 5, 5, ritual, 4, 6, 7, 8])
        game.duel_ready(before_deal=lambda g: g.arrange_deck(0, [5, 5, 5, ritual, 4]))
        for _ in range(3):
            slot = next(i for i, c in enumerate(game.duel()[0]["hand"]) if c and c["id"] == 5)
            game.play_card(slot, face_up=True)
            game.end_turn()
        slot = next(i for i, c in enumerate(game.duel()[0]["hand"]) if c and c["id"] == ritual)
        game.play_card(slot)
        game.step(120)
        summoned = [c["id"] for c in game.duel()[0]["monsters"] if c]
        assert summoned == [1], game.duel()
        assert game.u16("gDuel_wCardEffectFlags") == 0
        print("converted ritual: consumed three tributes and summoned Blue-Eyes", flush=True)
    print("All 20 monster types, magic-to-monster conversion, equip and ritual passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=ROOT / "tmp/pc/game32/memories-pc")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out:
        run(args.executable.resolve(), args.out.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="fm-card-types-") as folder:
            run(args.executable.resolve(), Path(folder))
