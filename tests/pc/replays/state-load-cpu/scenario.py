"""Save states and the end of VSync(0) (fixed in "Port: a loaded state
finishes the VSync(0) it resumes in"). A state is saved while the CPU
duelist thinks, 25 VBlanks into its turn; the game plays on, the state is
loaded in the same game and the same 600 frames are played again: every
frame must hash the same. Before the fix the load left VSync's last count a
frame behind, the CPU (which thinks until VSync(1) says the frame is spent)
stopped after one step and played a frame late: the frames parted at the
first one."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools/pc"))
from yfm_control import Game  # noqa: E402

SETTINGS = {"mod.3d-monsters": 0, "mod.hand-camera": 0, "mod.ai-hard-mode": 0, "mod.yamyi-mods": 0}
FRAMES = 600


def frames(game):
    hashes = []
    for _ in range(FRAMES):
        game.step(1)
        hashes.append(game.hash())
    return hashes


def run(executable, out):
    with Game(executable, out=out / "game", settings=SETTINGS) as game:
        game.goto("duel", opponent=2, deck="1-40")
        game.step(60)
        game.press("circle")
        game.duel_ready()
        game.play_card(0)
        game.wait_turn()
        game.press_until(lambda g: g.turn() != 0, "start", every=60, timeout=1200, what="the end of the turn")
        game.step(25)   # the CPU is thinking
        game.save("thinking.state")
        game.step(1)    # where a load of it stops: one frame in
        first = frames(game)
        game.load("thinking.state")
        again = frames(game)
        differ = next((i for i in range(FRAMES) if first[i] != again[i]), None)
        assert differ is None, f"frame {differ + 1} after the load differs from the same frame after the save"
