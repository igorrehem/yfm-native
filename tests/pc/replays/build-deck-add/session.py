"""The session this replay was recorded from, on the 32-bit build:

    python tools/pc/replay.py record tests/pc/replays/build-deck-add
        --session tests/pc/replays/build-deck-add/session.py --hash-every 4
        --settings mod.3d-monsters=0 mod.hand-camera=0 deck_slots=0

Build Deck with a forty-card deck (ids 1-40) and three of every card in the
chest: the first deck card back to the chest, then another card from the
chest into the deck (BuildDeck_AddCard). On arm64 that add crashed (an s32
record address sign-extended into a 64-bit offset, the game library being
at 0xC0000000); on Windows it did not, but the path is kept in step on both
widths. deck_slots=0 keeps the port's slot list (not in the frame) from
opening at the entry. Kept to record it again; playing does not run it."""
import struct

DECK = list(range(1, 41))


def run(game, out):
    game.step(900)   # the logos, the movie and the title
    game.poke("gDuel_awPlayerDeck", struct.pack("<40H", *DECK))
    game.poke("gLibrary_abCardChest", bytes([3]) * 722)
    game.goto("build_deck")
    game.step(120)
    for key, after in (("right", 40), ("cross", 30), ("left", 40), ("down", 10), ("cross", 60)):
        game.press(key, hold=6, after=after)
    game.step(60)
