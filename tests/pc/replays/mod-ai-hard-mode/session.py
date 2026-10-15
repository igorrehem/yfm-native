"""The session this replay was recorded from, on the 32-bit build with the
AI Hard Mode mod on (its default settings) and every other code mod off:

    python tools/pc/replay.py record tests/pc/replays/mod-ai-hard-mode
        --session tests/pc/replays/mod-ai-hard-mode/session.py --hash-every 4
        --settings mod.3d-monsters=0 mod.hand-camera=0 mod.ai-hard-mode=1
                   mod.yamyi-mods=0 mod.drop-missing-cards=0

A duel against Jono over six of the opponent's turns, each planned by the
mod (hand plays, fusion chains, guardian stars, attacks): the player sets a
card face down and ends the turn. The 64-bit game must draw every frame the
same, and so make the same choices (the 64-bit mod SDK's milestone M1).
Kept to record it again; playing does not run it."""

JONO = 3
DECK = "1-40"


def run(game, out):
    game.goto("duel", opponent=JONO, deck=DECK)
    game.duel_ready()
    for turn in range(6):
        if game.duel_over():
            break
        game.play_card(turn % 5)
        if game.duel_over():
            break
        if turn == 3:
            game.shot(out / "field.png")
        game.end_turn()
    game.step(120)
