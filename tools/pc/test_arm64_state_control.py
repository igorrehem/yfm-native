#!/usr/bin/env python3
"""Exercise native states through the game's ordinary control channel."""

import argparse
import os
from pathlib import Path

from gameplay_inputs import deck_editor_inputs
from yfm_control import ROOT, ControlError, Game


def incompatible(data, tag, offset=0):
    """Keep container integrity valid while changing a compatibility field."""
    image = bytearray(data)
    at = 16
    while at < len(image):
        length = int.from_bytes(image[at + 16 : at + 20], "little")
        if image[at : at + 16].rstrip(b"\0") == tag.encode():
            image[at + 20 + (offset if offset >= 0 else length + offset)] ^= 1
            break
        at += 20 + length
    else:
        raise AssertionError(f"missing {tag}")
    value = 14695981039346656037
    for byte in image[:-28]:
        value = ((value ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    image[-8:] = value.to_bytes(8, "little")
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--binary", type=Path, default=ROOT / "tmp/pc/macos/memories-arm64"
    )
    parser.add_argument(
        "--disc", type=Path, default=ROOT / "game/YGOFM Vanilla (Base).bin"
    )
    args = parser.parse_args()
    folder = ROOT / f"tmp/arm64-states/control-{os.getpid()}"
    mods = folder / "mods"
    mods.mkdir(parents=True)
    with Game(
        args.binary,
        out=folder,
        mods_dir=mods,
        env={
            "MEMORIES_DISC": str(args.disc.resolve()),
            "MEMORIES_INPUT": ",".join(
                part
                for part in deck_editor_inputs().split(",")
                if int(part.split(":")[0]) < 7999
            )
            + ",7999:0",
        },
    ) as game:
        while game.frame < 8000:
            game.step(min(1000, 8000 - game.frame))
        saved = game.save("deck.state")
        assert saved.stat().st_size > 2 * 1024 * 1024
        game.step(200)
        # The control reply advances one VSync; the sound driver's resident
        # work area at 0x801e0000 keeps ticking with the host audio clock.
        # Compare the complete game image, overlays and save/deck data.
        expected = game.peek(0x80000000, 0x1E0000)
        for _ in range(3):
            frame = game.frame
            game.load(saved)
            assert game.frame > frame, "presented frames must stay monotonic"
            game.step(199)
            actual = game.peek(0x80000000, 0x1E0000)
            if actual != expected:
                (folder / "expected.ram").write_bytes(expected)
                (folder / "actual.ram").write_bytes(actual)
            assert actual == expected, "repeated load did not reproduce guest RAM"
        data = saved.read_bytes()
        for label, broken in [
            ("corrupt", data[:1000] + bytes([data[1000] ^ 1]) + data[1001:]),
            ("truncated", data[:-8]),
            ("i386", data[:8] + (3).to_bytes(4, "little") + data[12:]),
            ("mods", incompatible(data, "mod-set")),
            ("language", incompatible(data, "language")),
            ("executable", incompatible(data, "arm64-entry", -16)),
        ]:
            path = folder / (label + ".state")
            path.write_bytes(broken)
            before = game.peek(0x80000000, 2 * 1024 * 1024)
            try:
                game.load(path)
            except ControlError:
                pass
            else:
                raise AssertionError(f"{label} state was accepted")
            assert game.peek(0x80000000, 2 * 1024 * 1024) == before, (
                f"{label} mutated the game"
            )
        game.step(10)
    autosaves = folder / "autosaves"
    with Game(
        args.binary,
        out=folder / "auto-run",
        mods_dir=mods,
        env={
            "MEMORIES_DISC": str(args.disc.resolve()),
            "MEMORIES_AUTOSAVE": "1",
            "MEMORIES_AUTOSAVE_DIR": str(autosaves),
        },
    ) as game:
        game.step(250)
        assert all((autosaves / f"auto{i}.state").is_file() for i in range(1, 4))
        game.load(autosaves / "auto3.state")
        game.step(60)
    print(
        f"ARM64 control save, three reloads, game RAM replay and rejected files passed; {folder}"
    )


if __name__ == "__main__":
    main()
