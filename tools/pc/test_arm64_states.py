#!/usr/bin/env python3
"""Native save-state replay across fresh processes; requires an owned US disc."""

import argparse
import os
from pathlib import Path

from gameplay_inputs import deck_editor_inputs
from gameplay_test_support import ROOT, run_game


def run(binary, disc, folder, label, settings, *, require_duel=True):
    user = folder / "user"
    mods = folder / "mods"
    mods.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("MEMORIES_")}
    env.update(
        MEMORIES_HEADLESS="1",
        MEMORIES_NO_AUDIO="1",
        MEMORIES_NO_GAMEPAD="1",
        MEMORIES_NO_UPDATE_CHECK="1",
        MEMORIES_SPEED="-1",
        MEMORIES_TRACE_GAMEPLAY="1",
        MEMORIES_DISC=str(disc),
        MEMORIES_USER_DIR=str(user),
        MEMORIES_MODS_DIR=str(mods),
        MEMORIES_INPUT=deck_editor_inputs(),
        MEMORIES_DUMP_FRAME="16800",
        MEMORIES_DUMP_PATH=str(folder / (label + ".ppm")),
    )
    env.update(settings)
    if env.get("SDL_VIDEODRIVER") == "dummy":
        env.pop("MEMORIES_HEADLESS", None)
    log = folder / (label + ".log")
    text = run_game(binary, env, log)
    if require_duel:
        assert "mode=c3 sub=81" in text, f"deck did not return to duel: {log}"
    return text


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--binary", type=Path, default=ROOT / "tmp/pc/macos/memories-arm64")
    p.add_argument("--disc", type=Path, default=ROOT / "game/YGOFM Vanilla (Base).bin")
    args = p.parse_args()
    binary, disc = args.binary.resolve(), args.disc.resolve()
    if not binary.is_file() or not disc.is_file():
        p.error("build and user-owned disc required")
    folder = ROOT / f"tmp/arm64-states/run-{os.getpid()}"
    folder.mkdir(parents=True, exist_ok=False)
    state = folder / "deck.state"
    first = run(binary, disc, folder, "save", {"MEMORIES_SAVE_STATE": f"8000:{state}"})
    assert state.is_file() and state.stat().st_size > 2 * 1024 * 1024
    assert "ARM64 state saved:" in first
    # Upstream's presented-frame counter stays monotonic across a load.
    # Boot loads at frame 30, so shift only the remaining controller events.
    remaining = ",".join(
        f"{int(part.split(':')[0]) - 8000 + 30}:{part.split(':')[1]}"
        for part in deck_editor_inputs().split(",")
        if int(part.split(":")[0]) > 8000
    )
    second = run(
        binary,
        disc,
        folder,
        "load",
        {
            "MEMORIES_LOAD_STATE": str(state),
            "MEMORIES_INPUT": remaining,
            "MEMORIES_DUMP_FRAME": str(16800 - 8000 + 30),
        },
    )
    assert "ARM64 state loading:" in second

    # Compare completed gameplay records, including RNG-driven deck order,
    # hand cards, LP and the rendered frame after the same remaining inputs.
    def ending(text):
        lines = text.splitlines()
        at = max(
            i for i, line in enumerate(lines) if line.startswith("gameplay frame=")
        )
        return lines[at + 1 :]

    assert ending(first) == ending(second), f"restored gameplay differs: {folder}"
    assert (folder / "save.ppm").read_bytes() == (folder / "load.ppm").read_bytes(), (
        f"restored pixels differ: {folder}"
    )
    text = run(
        binary,
        disc,
        folder,
        "sdl-states",
        {
            "MEMORIES_INPUT": ",".join(
                part
                for part in deck_editor_inputs().split(",")
                if int(part.split(":")[0]) < 7999
            )
            + ",7999:0",
            "MEMORIES_DUMP_FRAME": "8800",
            "SDL_VIDEODRIVER": "dummy",
            "SDL_RENDER_DRIVER": "software",
            "SDL_AUDIODRIVER": "dummy",
            "MEMORIES_STATE_DIR": str(folder / "slots"),
            "MEMORIES_SDL_SCRIPT": "8000:key:f5,8200:key:f7,8400:key:f7,8600:key:f7",
        },
        require_duel=False,
    )
    assert (folder / "slots/slot1.state").is_file(), "SDL F5 did not save"
    assert text.count("ARM64 state loading:") == 3, "SDL F7 did not restore three times"
    assert (folder / "sdl-states.ppm").is_file(), "SDL did not finish after loading"
    print(
        f"ARM64 fresh-process deck replay, identical pixels and SDL F5/F7 reloads passed; {folder}",
        flush=True,
    )


if __name__ == "__main__":
    main()
