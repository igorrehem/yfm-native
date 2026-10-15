"""The session this replay was recorded from, on the 32-bit build with the
code mods off and this folder's data mods on (mods.py):

    python tools/pc/replay.py record tests/pc/replays/x64-data-mods
        --session tests/pc/replays/x64-data-mods/session.py
        --mods tests/pc/replays/x64-data-mods/mods.py --hash-every 4
        --settings mod.3d-monsters=0 mod.hand-camera=0 mod.ai-hard-mode=0
                   mod.yamyi-mods=0 mod.drop-missing-cards=0

The main menu and a duel under the recolored sheets, with the card-pack's
two cards (723 and 724) in the player's deck, a few turns of presses, then
the Library. The 64-bit game must draw every frame the same (the data mods
gate of milestone X3). Kept to record it again; playing does not run it."""

PRESSES = ["cross", "right", "cross", "left", "cross", "down", "cross", "circle", "up", "cross", "triangle", "cross"]


def run(game, out):
    game.step(900)   # the logos, the movie and the title, recolored
    game.goto("duel", opponent=2, deck="723-724,1-38")
    game.step(60)
    game.press("circle")
    game.duel_ready()
    for turn in range(6):
        for key in PRESSES:
            game.press(key, hold=6, after=24)
        game.step(90)
    game.goto("library")
    game.step(120)
    for key in ["right"] * 6 + ["down"] * 4 + ["cross", "circle"]:
        game.press(key, hold=6, after=20)
    game.step(60)
