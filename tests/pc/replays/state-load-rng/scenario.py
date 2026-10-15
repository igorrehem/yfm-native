"""Save states and the game's random seed (fixed in "Port: save states carry
the game's random seed"). A pack is bought from a state, the state is loaded
again in the same game, and the same pack is bought with the same presses:
it must deal the same cards. Before the fix the seed was not in the state,
so the second purchase dealt other cards. The pack is test_packs.py's test
mod, made in the run's folder; the Password screen is reached with goto."""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools/pc"))
import test_packs as packs  # noqa: E402
from yfm_control import Game  # noqa: E402

SETTINGS = {"mod.3d-monsters": 0, "mod.hand-camera": 0, "mod.ai-hard-mode": 0, "mod.packs-test": 1}


def buy(game):
    """Triangle, Cross (BUY / QUIT), Cross (BUY), then Square once the first card turns: the list."""
    game.presses("triangle", "cross", "cross", after=64)
    game.step(160)
    game.press("square")
    game.step(120)
    return game.peek(packs.CHEST + 1, 722)


def run(executable, out):
    (out / "mods").mkdir(parents=True, exist_ok=True)
    packs.make_mod(out / "mods")
    with Game(executable, out=out / "game", settings=SETTINGS, mods_dir=out / "mods") as game:
        game.goto("password")   # the Password screen, with the pack shop
        game.step(300)
        game.poke("gLibrary_dwStarchips", struct.pack("<I", 1000))
        before = game.peek(packs.CHEST + 1, 722)
        game.save("rich.state")
        game.step(1)   # where a load of it stops: one frame in
        first = buy(game)
        dealt = {card + 1: first[card] - before[card] for card in range(722) if first[card] != before[card]}
        assert game.u32("gLibrary_dwStarchips") == 1000 - packs.PRICE, "the pack was not bought"
        assert sum(dealt.values()) == packs.COUNT, f"the pack dealt {dealt}"
        game.load("rich.state")
        second = buy(game)
        again = {card + 1: second[card] - before[card] for card in range(722) if second[card] != before[card]}
        assert again == dealt, f"the same pack from the same state dealt {dealt}, then {again} after loading it"
