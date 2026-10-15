"""The session this replay was recorded from, on the 32-bit build with the
3D Monsters mod on and every other code mod off (its "3D models" style):

    python tools/pc/replay.py record tests/pc/replays/mod-3d-monsters
        --session tests/pc/replays/mod-3d-monsters/session.py --hash-every 4
        --settings mod.3d-monsters=1 mod.hand-camera=0 mod.ai-hard-mode=0
                   mod.yamyi-mods=0 mod.drop-missing-cards=0

A duel against Simon Muran with a deck of monsters: each turn one is played
face up, so the field fills with models standing on their cards, and from
the second turn the monsters attack, with the 3D battles (the models facing
each other on the big cards). The 64-bit game must draw every frame the
same (the 64-bit mod SDK's milestone M1). Kept to record it again; playing
does not run it."""

SIMON = 1
DECK = "1-40"   # monsters only


def run(game, out):
    game.goto("duel", opponent=SIMON, deck=DECK)
    game.duel_ready()
    for turn in range(5):
        if game.duel_over():
            break
        game.play_card(0, face_up=True)
        if game.duel_over():
            break
        if turn:
            field = game.field()
            for column in range(5):
                if game.duel_over() or game.turn() != 0:
                    break
                if field[2][column]:
                    theirs = [index for index, card in enumerate(game.field()[1]) if card]
                    try:
                        game.attack(column, theirs[0] if theirs else None)
                    except Exception:   # the monster cannot attack (defence, attacked): go on
                        pass
                    break
        if turn == 2:
            game.shot(out / "field.png")
        if game.duel_over():
            break
        game.end_turn()
    game.step(120)
