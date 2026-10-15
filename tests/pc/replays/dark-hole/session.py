"""The session this replay was recorded from, on the 32-bit build:

    python tools/pc/replay.py record tests/pc/replays/dark-hole
        --session tests/pc/replays/dark-hole/session.py --hash-every 4
        --settings mod.3d-monsters=0 mod.hand-camera=0

Dark Hole (336), effect 17, against Simon Muran, as test_duel_effects.py's
"dark-hole" scenario plays it: its bolt (func_8014FABC, bolt_vertices.c)
built its vertex steps from an s32 address plus a 64-bit offset, which the
64-bit build sign-extended out of guest RAM, so the 64-bit game crashed as
the card resolved. Both widths must draw every frame the same. Kept to
record it again; playing the replay does not run it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools/pc"))
from test_duel_effects import SCENARIOS, SIMON  # noqa: E402


def run(game, out):
    game.step(900)   # the logos, the movie and the title
    _, deck, before_deal, play = next(s for s in SCENARIOS if s[0] == "dark-hole")
    game.goto("duel", opponent=SIMON, deck=deck)
    game.duel_ready(before_deal=before_deal)
    play(game)
    game.step(240)
