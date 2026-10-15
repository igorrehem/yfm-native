"""A loaded save state goes on as the game that saved it did.

One game saves a state and plays on, writing a hash of every frame; a second
game, a new process, loads the state at its frame 30 and plays the same
input: frame for frame, the pictures must be the same. Each case runs 2000
frames past the save. Before states kept the clock's phase, the campaign map
parted after 181 or 357 frames (a file finished loading a frame apart), and
before the Windows build kept the game's small data in them, the opening
movie at once (its decode slot, D_8009B066).

    test_state_resume.py [--executable EXE] [--out DIR] [case...]
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tmp/pc/state-resume-test"
EXECUTABLE = ROOT / ("tmp/pc/win32/memories-pc.exe" if sys.platform == "win32" else "tmp/pc/game32/memories-pc")
LOAD_FRAME = 30   # MEMORIES_LOAD_STATE is acted on at the first state point from this frame on (state.c)
FRAMES = 2000

# A fresh game's NEW GAME (test_packs.py's opening), then the campaign map
# (MEMORIES_MODE_AT runs mode 5 in its place) and a walk on it with the
# menus opened and closed, which loads files from the disc as it goes.
OPENING = "910:0008,916:0000,1000:0040,1006:0000,1020:0040,1026:0000,1040:0040,1046:0000,1060:0040,1066:0000," \
          "1100:4000,1106:0000"
WALK = ["4000", "0020", "4000", "0080", "2000", "4000", "0010", "4000", "0040", "4000", "1000", "4000", "8000"]


def walk(start, count, gap=15, hold=5):
    """Presses from frame `start`: one every `gap` frames, held `hold`."""
    events = []
    for i in range(count):
        frame = start + gap * i
        events += [(frame, WALK[i % len(WALK)]), (frame + hold, "0000")]
    return events


CASES = {
    # name: (frame the state is saved at, MEMORIES_MODE_AT, input before the save, input after it)
    "map": (1503, "1000:5", OPENING, walk(1504, FRAMES // 15)),
    "map-b": (1477, "1000:5", OPENING, walk(1478, FRAMES // 15)),
    "movie": (400, None, "", []),
}


def run(executable, folder, frames, mode_at=None, events="", state=None, save_at=None):
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    settings = folder / "settings.txt"
    settings.write_text("mod.3d-monsters=0\nmod.hand-camera=0\nmod.ai-hard-mode=0\nmod.yamyi-mods=0\n")
    env = {key: value for key, value in os.environ.items() if not key.startswith("MEMORIES_")}
    env.update(MEMORIES_HEADLESS="1", MEMORIES_DETERMINISTIC="1", MEMORIES_NO_AUDIO="1", MEMORIES_NO_GAMEPAD="1",
               MEMORIES_NO_UPDATE_CHECK="1", MEMORIES_WATCHDOG="0", MEMORIES_SPEED="-1",
               MEMORIES_SETTINGS=str(settings), MEMORIES_USER_DIR=str(folder / "user"),
               MEMORIES_FRAME_HASHES=str(folder / "hashes.txt"), MEMORIES_DUMP_FRAME=str(frames),
               MEMORIES_DUMP_PATH=str(folder / "last.ppm"))
    if events:
        env["MEMORIES_INPUT"] = events
    if mode_at:
        env["MEMORIES_MODE_AT"] = mode_at
    if save_at:
        env["MEMORIES_SAVE_STATE"] = f"{save_at}:{folder / 'point.state'}"
    if state:
        env["MEMORIES_LOAD_STATE"] = str(state)
    if "MEMORIES_DISC" in os.environ:
        env["MEMORIES_DISC"] = os.environ["MEMORIES_DISC"]
    command = [str(executable)]
    if executable.suffix == ".exe" and sys.platform != "win32":
        command = ["wine", str(executable)]
        env.update(WINEDLLOVERRIDES="mscoree,mshtml=", WINEDEBUG="-all")
    with (folder / "run.log").open("w") as log:
        subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
    hashes = {}
    for line in (folder / "hashes.txt").read_text().splitlines():
        frame, value = line.split()
        hashes[int(frame)] = value
    return hashes, folder / "run.log"


def script(events):
    return ",".join(f"{frame}:{bits}" for frame, bits in events)


def check_case(executable, out, name):
    save_at, mode_at, before, after = CASES[name]
    saver, _ = run(executable, out / name / "saver", save_at + FRAMES + 1, mode_at,
                   ",".join(part for part in (before, script(after)) if part), save_at=save_at)
    state = out / name / "saver" / "point.state"
    if not state.exists():
        print(f"state-resume: {name}: FAILED: the saver wrote no state at frame {save_at}")
        return False
    # The loader's frame count is its own: frame LOAD_FRAME + k is the saver's save_at + k.
    shift = save_at - LOAD_FRAME
    loader, log = run(executable, out / name / "loader", LOAD_FRAME + FRAMES + 1,
                      events=script((frame - shift, bits) for frame, bits in after), state=state)
    if "state loaded" not in log.read_text(errors="replace"):
        print(f"state-resume: {name}: FAILED: the state was not loaded (see {log})")
        return False
    for k in range(1, FRAMES + 1):
        expected, got = saver.get(save_at + k), loader.get(LOAD_FRAME + k)
        if expected is None or got is None:
            print(f"state-resume: {name}: FAILED: no hash for frame {k} after the load")
            return False
        if expected != got:
            print(f"state-resume: {name}: FAILED: frame {k} after the load differs ({expected} vs {got})")
            return False
    distinct = len({saver[save_at + k] for k in range(1, FRAMES + 1)})
    print(f"state-resume: {name}: ok: {FRAMES} frames after the load as after the save ({distinct} distinct)")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--executable", type=Path, default=EXECUTABLE, help=f"the game (default: {EXECUTABLE})")
    parser.add_argument("--out", type=Path, default=OUT, help=f"where the runs are kept (default: {OUT})")
    parser.add_argument("cases", nargs="*", default=list(CASES), help=f"cases (default: all of {', '.join(CASES)})")
    arguments = parser.parse_args()
    unknown = [case for case in arguments.cases if case not in CASES]
    if unknown:
        parser.error(f"unknown case {', '.join(unknown)}")
    results = [check_case(arguments.executable.resolve(), arguments.out.resolve(), case) for case in arguments.cases]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
