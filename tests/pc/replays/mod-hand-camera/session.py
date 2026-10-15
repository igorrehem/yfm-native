"""The session this replay was recorded from, on the 32-bit build with the
Hand Camera mod on and every other code mod off:

    python tools/pc/replay.py record tests/pc/replays/mod-hand-camera
        --session tests/pc/replays/mod-hand-camera/session.py --hash-every 4
        --settings mod.3d-monsters=0 mod.hand-camera=1 mod.ai-hard-mode=0
                   mod.yamyi-mods=0 mod.drop-missing-cards=0

A duel against Simon Muran: while the hand is up, L1 and R1 turn the camera
around the mat and L3 and R3 zoom it, over two turns, with a card played
and the opponent's turn between them (the game's own camera moves carry it
back). The 64-bit game must draw every frame the same (the 64-bit mod SDK's
milestone M1). Kept to record it again; playing does not run it."""

SIMON = 1
DECK = "1-40"


def turn_camera(game):
    game.wait_turn(("hand",))
    game.press("l1", hold=90, after=10)
    game.press("l3", hold=40, after=10)
    game.press("r1", hold=150, after=10)
    game.press("r3", hold=70, after=10)
    game.press(["l1", "l3"], hold=30, after=20)


def run(game, out):
    game.goto("duel", opponent=SIMON, deck=DECK)
    game.duel_ready()
    turn_camera(game)
    game.shot(out / "turned.png")
    game.play_card(0, face_up=True)
    game.end_turn()
    turn_camera(game)
    game.play_card(1)
    game.step(120)
