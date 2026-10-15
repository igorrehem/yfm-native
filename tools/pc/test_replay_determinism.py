#!/usr/bin/env python3
"""Compare a recorded replay across two fresh local game processes.

This checks whether one build repeats its own recorded hashes and end marker.
It does not compare those hashes with a replay recorded by another platform.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from replay import Replay, completed, parse, play_recorded, report  # noqa: E402


def compare_hashes(left: dict, right: dict, name: str) -> bool:
    first, second = left["H"], right["H"]
    for key in sorted(first.keys() | second.keys()):
        a, b = first.get(key), second.get(key)
        if a != b:
            index, frame = key
            report(f"replay determinism: {name}: first H difference at VBlank {index} "
                   f"(frame {frame}): run 1 {a or 'missing'}, run 2 {b or 'missing'}")
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--replay", type=Path, default=ROOT / "tests/pc/replays/menus",
                        help="recorded replay folder (default: tests/pc/replays/menus)")
    parser.add_argument("--binary", type=Path, default=ROOT / "tmp/pc/macos/memories-arm64",
                        help="game executable to launch twice")
    parser.add_argument("--out", type=Path, default=ROOT / "tmp/pc/replay-determinism",
                        help="parent for isolated run artifacts")
    parser.add_argument("--timeout", type=float, default=900,
                        help="maximum seconds for each process (default: 900)")
    args = parser.parse_args()

    replay_path = args.replay.expanduser().resolve()
    executable = args.binary.expanduser().resolve()
    out_root = args.out.expanduser().resolve()
    if not replay_path.is_dir():
        parser.error(f"--replay must be a replay folder: {replay_path}")
    if not executable.is_file():
        parser.error(f"--binary does not exist: {executable}")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if out_root == (ROOT / "tests/pc/replays").resolve() or (ROOT / "tests/pc/replays").resolve() in out_root.parents:
        parser.error("--out must stay outside tests/pc/replays; this runner never writes goldens")

    replay = Replay(replay_path)
    if replay.meta.get("kind") != "recorded":
        parser.error("scripted replays do not contain recorded H/E markers and cannot be compared")
    expected = parse(replay.file(replay.meta["recording"]))
    if replay.meta.get("header", {}).get("clock") == "real" or expected["F"].get("clock") == "real":
        parser.error("real-clock recordings cannot be replayed deterministically; record with the virtual clock")
    if expected["E"] is None:
        parser.error("recorded replay has no E end marker")
    if not expected["H"]:
        parser.error("recorded replay has no H frame hashes")

    out_root.mkdir(parents=True, exist_ok=True)
    run_root = Path(tempfile.mkdtemp(prefix=f"{replay.name}-", dir=out_root))
    recordings: list[Path] = []
    for number in (1, 2):
        actual = play_recorded(replay, executable, run_root / f"run-{number}", args.timeout)
        if actual is None:
            report(f"replay determinism: {replay.name}: run {number} failed; artifacts kept at {run_root}")
            return 1
        observed = parse(actual)
        if not observed["H"]:
            report(f"replay determinism: {replay.name}: run {number} wrote no H frame hashes; artifacts kept at {run_root}")
            return 1
        if not completed(expected, observed, f"{replay.name} run {number}"):
            report(f"replay determinism: artifacts kept at {run_root}")
            return 1
        recordings.append(actual)

    first, second = map(parse, recordings)
    ok = first["E"] == second["E"]
    if not ok:
        report(f"replay determinism: {replay.name}: E markers differ: run 1 {first['E']}, run 2 {second['E']}")
    ok = compare_hashes(first, second, replay.name) and ok
    if not ok:
        report(f"replay determinism: artifacts kept at {run_root}")
        return 1

    report(f"replay determinism: {replay.name}: {len(first['H'])} H entries and E {first['E']} "
           f"match across two fresh processes")
    report(f"replay determinism: artifacts kept at {run_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
