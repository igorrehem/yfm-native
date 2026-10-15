"""The session this replay was recorded from, on the 32-bit build with Yamyi
Mods on (its default settings) and every other code mod off:

    python tools/pc/replay.py record tests/pc/replays/mod-yamyi-mods
        --session tests/pc/replays/mod-yamyi-mods/session.py --hash-every 4
        --settings mod.3d-monsters=0 mod.hand-camera=0 mod.ai-hard-mode=0
                   mod.yamyi-mods=1 mod.drop-missing-cards=0

The mode-select wheel, reached from the debug menu as Main_RunMenu opens
it (D_8009B26D = 5, then D_8009B26C = 8: two pokes, which the recording
keeps), with every card shown in the Library (the chest's flags, poked as
tools/pc/test_yamyi_mods.py's fixture sets them). The Library's grid, the
cursor moved across it (the mod's drop-odds panel is drawn over the picture
by the host, which the frame hashes do not cover; the rows it builds from
the disc are), then back to the wheel and Circle: the mod's "RETURN TO
TITLE?" prompt, NO (the wheel stays), Circle again, YES, and the title.
The 64-bit game must draw every frame the same (the 64-bit mod SDK's
milestone M1). Kept to record it again; playing does not run it."""

CHEST = 0x801D0250   # a byte per card: 1, in the chest (shown in the Library)


def run(game, out):
    game.goto("debug")
    game.step(60)
    game.poke("D_8009B26D", bytes([5]))
    game.poke("D_8009B26C", bytes([8]))
    game.step(200)
    game.poke(CHEST, bytes([1]) * 722)
    for key in ["down"] * 3:   # LIBRARY
        game.press(key, hold=6, after=30)
    game.press("cross", hold=6, after=200)
    for key in ["right"] * 4 + ["down"] * 2 + ["left"]:
        game.press(key, hold=6, after=24)
    game.step(60)
    game.shot(out / "library.png")
    game.press("circle", hold=6, after=240)   # the wheel
    game.press("circle", hold=6, after=90)    # the prompt
    game.shot(out / "prompt.png")
    game.press("cross", hold=6, after=90)     # NO, the default: the wheel stays
    game.press("circle", hold=6, after=90)
    game.press("left", hold=6, after=30)      # YES
    game.shot(out / "yes.png")
    game.press("cross", hold=6, after=300)    # to the title
    game.shot(out / "title.png")
