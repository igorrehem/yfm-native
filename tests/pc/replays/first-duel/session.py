"""The session this replay was recorded from (tools/pc/replay.py record
tests/pc/replays/first-duel --session tests/pc/replays/first-duel/session.py
--hash-every 4): boot, a new game, the story to the first duel, the first
card played (tools/pc/examples/control_first_duel.py). Kept to record it
again; playing the replay does not run it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools/pc/examples"))
from control_first_duel import drive  # noqa: E402


def run(game, out):
    drive(game, {})
