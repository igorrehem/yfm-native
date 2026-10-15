#!/usr/bin/env python3
"""Save at the shop, load afresh, then sort the standalone Build Deck menu."""

import argparse
import os
import struct
from pathlib import Path

from gameplay_inputs import inputs
from gameplay_test_support import ROOT, run


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--disc", type=Path, default=ROOT / "game/YGOFM Vanilla (Base).bin")
    p.add_argument("--binary", type=Path, default=ROOT / "tmp/pc/macos/memories-arm64")
    args = p.parse_args()
    disc = args.disc.resolve()
    binary = args.binary.resolve()
    if not binary.is_file():
        p.error("build the requested executable first")
    if not disc.is_file():
        p.error("a user-owned retail disc is required")
    folder = ROOT / f"tmp/arm64-save-load/run-{os.getpid()}"
    folder.mkdir(parents=True, exist_ok=False)
    opening = ",".join(
        part for part in inputs().split(",") if int(part.split(":")[0]) <= 4906
    )
    events = [(5600, "0040"), (5900, "0020"), (6200, "0020"), (6500, "4000")]
    events += [(f, "4000") for f in (6800, 7100, 7400, 7800, 8200, 8600)]
    events += [(f + 6, "0000") for f, _ in list(events)]
    text = run(
        folder,
        disc,
        opening + "," + ",".join(f"{f}:{b}" for f, b in sorted(events)),
        9000,
        "save",
        binary=binary,
    )
    assert "scene=45 location=13 deck=40" in text, f"did not reach card shop: {folder}"
    slot = folder / "user/saves/slot01.sav"
    data = slot.read_bytes()
    assert len(data) == 8192 and data[:2] == b"SC"
    assert all(struct.unpack_from("<40H", data, 0x200))
    assert data[0x7DC] == 45 and struct.unpack_from("<I", data, 0x604)[0] > 0
    assert data[0x200:0x880] == data[0x880:0xF00], "save payload copies differ"
    events = [
        (700, "0008"),
        (780, "0040"),
        (820, "4000"),
        (1100, "4000"),
        (1400, "4000"),
    ]
    events += [(f + 6, "0000") for f, _ in list(events)]
    text = run(
        folder,
        disc,
        ",".join(f"{f}:{b}" for f, b in sorted(events)),
        4000,
        "load",
        binary=binary,
    )
    assert "mode=c2 sub=00 scene=45 location=0 deck=40" in text, (
        f"fresh process did not restore campaign: {folder}"
    )
    assert slot.read_bytes() == data, "load unexpectedly changed the saved slot"
    # Reach standalone Build Deck through LOAD's real title menu. Cover
    # the retail grid alone and the PC slot chooser followed by that grid.
    events = [
        (700, "0008"),
        (780, "0040"),
        (820, "4000"),
        (1100, "4000"),
        (1400, "0040"),
        (1460, "0040"),
        (1550, "4000"),
        (2000, "0020"),
    ]
    events += [(f, "0008") for f in range(2200, 3600, 200)]
    events += [(3650, "0080")]
    events += [(f, "0001") for f in range(3900, 5300, 200)]
    events += [(5600, "2000")]
    for variant in ("retail", "slots", "keyboard"):
        enabled = variant != "retail"
        settings = {"MEMORIES_DECK_SLOTS": str(int(enabled))}
        sequence = events + ([(1850, "4000")] if enabled else [])
        if variant == "keyboard":
            # LOAD via pad, then confirm the PC slot, switch panels, sort and
            # leave through SDL keyboard events and ControlsRuntime_Key.
            sequence = [(f, b) for f, b in events if f < 1850]
            keys = [(1850, "x"), (2000, "right")]
            keys += [(f, "return") for f in range(2200, 3600, 200)]
            keys += [(3650, "left")]
            keys += [(f, "return") for f in range(3900, 5300, 200)]
            keys += [(5600, "s")]
            script = [(f, "keydown", k) for f, k in keys]
            script += [(f + 6, "keyup", k) for f, k in keys]
            settings.update(
                SDL_VIDEODRIVER="dummy",
                SDL_RENDER_DRIVER="software",
                SDL_AUDIODRIVER="dummy",
                MEMORIES_SDL_SCRIPT=",".join(
                    f"{f}:{op}:{k}" for f, op, k in sorted(script)
                ),
            )
        sequence += [(f + 6, "0000") for f, _ in list(sequence)]
        text = run(
            folder,
            disc,
            ",".join(f"{f}:{b}" for f, b in sorted(sequence)),
            6500,
            "deck-" + variant,
            settings,
            binary=binary,
        )
        assert "mode=c7" in text and "gameplay frame=6480 mode=c8" in text, (
            f"deck entry/exit failed: {folder}"
        )
        for pane in (0, 1):
            for choice in range(7):
                assert f"decklist pane={pane} sort={choice} " in text, (
                    f"missing pane {pane} sort {choice}: {folder}"
                )
        assert "deck=40 chest=0" in text and slot.read_bytes() == data
    print(
        f"ARM64 shop save, fresh-process load and standalone deck pad/SDL keyboard sorts passed; {folder}",
        flush=True,
    )


if __name__ == "__main__":
    main()
