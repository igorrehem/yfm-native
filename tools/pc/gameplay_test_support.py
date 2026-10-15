"""Isolated process execution for retail gameplay and save/load regressions."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAILURES = (
    "cannot run;",
    "using the native stand-in",
    "unimplemented game routine",
    "invalid guest data span",
    "fatal signal",
)


def clean_environment():
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("MEMORIES_")
    }


def run_game(binary, environment, log, *, timeout=240):
    """Keep diagnostics after failure and reject fallback execution."""
    try:
        with log.open("w") as stream:
            subprocess.run(
                [str(binary)],
                cwd=ROOT,
                env=environment,
                stdout=stream,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=timeout,
            )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"{log.stem}: game process failed; inspect {log}") from error
    text = log.read_text()
    for failure in FAILURES:
        assert failure not in text, f"{log.stem}: {failure}; inspect {log}"
    return text


def run(folder, disc, sequence, frames, label, settings=None, *, binary):
    mods = folder / "mods"
    mods.mkdir(exist_ok=True)
    env = clean_environment()
    env.update(
        MEMORIES_HEADLESS="1",
        MEMORIES_NO_AUDIO="1",
        MEMORIES_NO_GAMEPAD="1",
        MEMORIES_NO_UPDATE_CHECK="1",
        MEMORIES_SPEED="-1",
        MEMORIES_TRACE_GAMEPLAY="1",
        MEMORIES_DISC=str(disc),
        MEMORIES_USER_DIR=str(folder / "user"),
        MEMORIES_MODS_DIR=str(mods),
        MEMORIES_INPUT=sequence,
        MEMORIES_DUMP_FRAME=str(frames),
        MEMORIES_DUMP_PATH=str(folder / (label + ".ppm")),
    )
    env.update(settings or {})
    if env.get("SDL_VIDEODRIVER") == "dummy":
        # Exercise SDL's event pump without opening an OS window.
        env.pop("MEMORIES_HEADLESS", None)
    log = folder / (label + ".log")
    text = run_game(binary, env, log)
    assert (folder / (label + ".ppm")).is_file(), f"missing completed frame: {log}"
    return text
