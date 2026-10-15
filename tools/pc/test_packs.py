#!/usr/bin/env python3
"""Live card packs test (built game and user-supplied disc; notes/card-packs.md).

Makes a pack mod of its own (a PNG drawn here, no game data), opens the
Password screen (the control client's goto, through the game's debug menu)
and gives it starchips, then buys from it with the triangle, BUY and a skip
to the list of what came, each purchase from the same state loaded in the
same game. It checks that the starchips drop by the price, that the chest
gains exactly the cards the pack dealt and the cards last awarded are they,
that a second purchase deals the same (the same input, the same numbers),
that a state saved while the cards turn over, resumed in a new process,
ends with the same chest, that a pack whose every card the player holds
"max_copies" of is refused (ALL OWNED, nothing paid) unless it says
"when_nothing_left": "sell", that a full chest is never sold a card it would
drop (the pack deals only cards with room, a pack of none is refused, and so
is one whose fixed card has no room), and that without the mod the triangle
does nothing. Artifacts stay in tmp/pc/packs-test (or --out); no player
saves are touched.

    python3 tools/pc/test_packs.py [--windows | --executable PATH] [--out DIR]
"""
import argparse
import json
from pathlib import Path
import shutil
import struct
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from yfm_control import Game  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tmp/pc/packs-test"
EXECUTABLE = ROOT / "tmp/pc/game32/memories-pc"
WINDOWS_EXECUTABLE = ROOT / "tmp/pc/win32/memories-pc.exe"

STARCHIPS = 0x801D07E0          # SaveDataState.starchips
CHEST = 0x801D0250 - 1          # gLibrary_abCardChest, by card id
RECENT = 0x801D07BC             # the cards last awarded, newest first
PRICE, COUNT = 120, 5
CARDS = [2, 3, 4, 5, 6, 7, 8, 9]
OWNED, OWNED_SOLD, OWNED_PRICE = [10, 11], [12, 13], 50   # held once each: packs of "max_copies": 1
FIXED, FIXED_PRICE = 14, 30     # the fourth pack's one fixed card
FULL = 250                      # copies of a card the disc's chest keeps
SETTINGS = {"mod.3d-monsters": 0, "mod.hand-camera": 0, "mod.ai-hard-mode": 0}

# The presses, as VBlanks after the state is loaded: △, ✕ (BUY / QUIT), ✕
# (BUY), then □ once the first card turns: the list. RIGHT picks the next pack.
BUY = [(30, "triangle"), (100, "cross"), (170, "cross"), (370, "square")]
REFUSE = [(30, "triangle"), (100, "right"), (170, "cross"), (240, "cross")]
SELL = [(30, "triangle"), (100, "right"), (170, "right"), (240, "cross"), (310, "cross")]
FIXED_BUY = [(30, "triangle"), (100, "right"), (170, "right"), (240, "right"), (310, "cross"), (380, "cross")]


def png(width, height):
    """An RGB PNG of our own: a diagonal gradient with a light frame."""
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            edge = x < 4 or y < 4 or x >= width - 4 or y >= height - 4
            rows += bytes((230, 230, 240) if edge else (40 + 150 * y // height, 30 + 120 * x // width, 150))
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b""))


def make_mod(mods):
    folder = mods / "packs-test"
    (folder / "packs").mkdir(parents=True, exist_ok=True)
    (folder / "packs" / "test.png").write_bytes(png(204, 192))
    manifest = {"id": "packs-test", "name": "Card packs test", "enabled": True,
                "packs": [{"id": "test", "name": "Test Pack", "image": "packs/test.png", "price": PRICE,
                           "count": COUNT, "tiers": {"common": {"odds": 9, "cards": CARDS[:6]},
                                                     "rare": {"odds": 1, "cards": CARDS[6:], "label": "RARE!"}},
                           "guarantee": {"rare": 1}},
                          {"id": "owned", "name": "Owned", "price": OWNED_PRICE, "count": 3, "max_copies": 1,
                           "tiers": {"common": {"cards": OWNED[:1]}, "rare": {"odds": 0, "cards": OWNED[1:]}},
                           "pity": {"rare": 2}, "stock": 3},
                          {"id": "owned-sold", "name": "Owned Sold", "price": OWNED_PRICE, "count": 3, "max_copies": 1,
                           "tiers": {"common": {"cards": OWNED_SOLD[:1]}, "rare": {"odds": 0, "cards": OWNED_SOLD[1:]}},
                           "pity": {"rare": 2}, "stock": 3, "when_nothing_left": "sell"},
                          {"id": "fixed", "name": "Fixed", "price": FIXED_PRICE, "count": 2,
                           "cards": CARDS[:1], "slots": [{"card": FIXED}, "cards"]}]}
    (folder / "mod.json").write_text(json.dumps(manifest, indent=4), encoding="utf-8")


def chunks(path):
    data = bytearray(path.read_bytes())
    at, found = 16, {}
    while at + 20 <= len(data):
        tag = data[at:at + 16].split(b"\0")[0].decode(errors="replace")
        size, = struct.unpack_from("<I", data, at + 16)
        found[tag] = at + 20
        at += 20 + size
    return data, found


# What the save's progress says, in the state's pack-shop chunk: pack_shop.c
# Screen's own fields, then packs.h PacksProgress (starchips spent, packs
# opened, and a PackProgress a pack: bought, opened, pity[16], used). The
# purchase below checks the place against the counts it must have made.
PROGRESS_AT = 280
PACK_PROGRESS = 44


def progress(path, pack):
    """(starchips spent, packs opened, bought, opened, pity by tier) of a pack
    by its place in the list."""
    data, found = chunks(path)
    at = found["pack-shop"] + PROGRESS_AT
    spent, opened_all = struct.unpack_from("<II", data, at)
    mine = at + 8 + PACK_PROGRESS * pack
    bought, opened = struct.unpack_from("<II", data, mine)
    return spent, opened_all, bought, opened, list(struct.unpack_from("<16H", data, mine + 8))


def check(condition, message):
    if not condition:
        sys.exit(f"packs: FAILED: {message}")
    print(f"packs: ok: {message}")


class Shop:
    """The Password screen of a game with (or without) the pack mod."""

    def __init__(self, executable, name, mods, with_mod=True):
        self.game = Game(executable, out=OUT / name, settings={**SETTINGS, "mod.packs-test": int(with_mod)},
                         mods_dir=mods)
        self.game.goto("password")
        self.game.step(300)   # the screen fades in

    def play(self, events, end, chest_full=(), save_at=None):
        """From the loaded state: the chest's cards in `chest_full` at 250, then
        the presses at their VBlanks; a state at `save_at`, if asked."""
        game = self.game
        start = game.vblank
        for card in chest_full:
            game.poke(CHEST + card, bytes([FULL]))
        for at, key in events + [(save_at, None), (end, None)]:
            if at is None:
                continue
            game.step(max(start + at - game.vblank, 0))
            if key:
                game.press(key, hold=6, after=0)
            elif at == save_at:
                game.save("turning.state")
        return self

    def chest(self):
        return self.game.peek(CHEST + 1, 722)

    def starchips(self):
        return self.game.u32(STARCHIPS)

    def recent(self):
        return list(struct.unpack("<5H", self.game.peek(RECENT, 2 * COUNT)))

    def progress(self, pack):
        return progress(self.game.save("progress.state"), pack)


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--windows", action="store_true", help="test the Windows build under Wine")
    parser.add_argument("--executable", type=Path, help="the game to test (default: the build for this host)")
    parser.add_argument("--out", type=Path, help=f"where the runs are kept (default: {OUT})")
    arguments = parser.parse_args()
    executable = WINDOWS_EXECUTABLE if arguments.windows else EXECUTABLE
    if arguments.executable:
        executable = arguments.executable.resolve()
    if arguments.out:
        OUT = arguments.out.resolve()
    shutil.rmtree(OUT, ignore_errors=True)
    mods = OUT / "mods"
    make_mod(mods)

    # The Password screen, given starchips and one copy of the owned packs' cards.
    shop = Shop(executable, "shop", mods)
    game = shop.game
    check("pack-shop" in chunks(game.save("screen.state"))[1],
          "a state of the Password screen with a pack mod has its pack-shop chunk")
    game.poke(STARCHIPS, struct.pack("<I", 1000))
    for card in OWNED + OWNED_SOLD:
        game.poke(CHEST + card, b"\x01")
    rich = game.save("rich.state")

    def from_rich(events, end, **options):
        game.load(rich)
        return shop.play(events, end, **options)

    before = from_rich([], 0).chest()
    after = from_rich(BUY, 490).chest()
    gained = {card + 1: after[card] - before[card] for card in range(722) if after[card] != before[card]}
    check(shop.starchips() == 1000 - PRICE, f"the starchips drop by the price ({PRICE})")
    check(sum(gained.values()) == COUNT and set(gained) <= set(CARDS),
          f"the chest gains the {COUNT} cards of the pack: {gained}")
    recent = shop.recent()
    check(sorted(recent) == sorted(card for card, n in gained.items() for _ in range(n)),
          f"the cards last awarded are the pack's: {recent}")
    check(any(card in CARDS[6:] for card in recent), "the guarantee gives a rare")
    check(shop.progress(0)[:4] == (PRICE, 1, 1, 1),
          f"the save's progress counts it: {PRICE} starchips spent, one pack opened, bought once")
    check(from_rich(BUY, 490).chest() == after, "the same input deals the same pack")

    # A state saved while the first card is up, resumed in a new process.
    from_rich(BUY[:3], 300, save_at=300)
    resumed = Shop(executable, "resumed", mods)
    resumed.game.load(OUT / "shop" / "turning.state")
    resumed.play([(30, "square")], 170)
    check(resumed.chest() == after, "a state saved mid-reveal keeps the cards, once, in a new process")
    check(resumed.starchips() == 1000 - PRICE, "and the starchips paid, once")
    resumed.game.quit()

    # Every card held "max_copies" times: refused by default (the list, then
    # BUY / QUIT with BUY grey, ✕ taking QUIT), sold with "sell".
    from_rich(REFUSE, 490)
    check(shop.starchips() == 1000 and shop.chest() == before,
          "a pack with nothing left for the player is refused: no starchips, no cards")
    check(shop.progress(1) == (0, 0, 0, 0, [0] * 16),
          "and its stock, its openings, the pity and the save's counts are untouched")
    from_rich(SELL, 490)
    check(shop.starchips() == 1000 - OWNED_PRICE and shop.chest() == before,
          "\"when_nothing_left\": \"sell\" sells it: the price paid, every slot empty")
    sold = shop.progress(2)
    check(sold[:4] == (OWNED_PRICE, 1, 1, 1) and sold[4][1] == 1,
          "and counts it: a purchase of the stock, an opening, a pack without its rare for the pity")

    # A full chest: the commons at 250, the pack deals none of them; every
    # card at 250, it is refused; a fixed card at 250 refuses its pack.
    held = from_rich([], 0, chest_full=CARDS[:6]).chest()
    dealt = from_rich(BUY, 490, chest_full=CARDS[:6]).chest()
    gained = {card + 1: dealt[card] - held[card] for card in range(722) if dealt[card] != held[card]}
    check(shop.starchips() == 1000 - PRICE and gained and set(gained) <= set(CARDS[6:]) and
          not set(shop.recent()) & set(CARDS[:6]),
          f"a chest full of the commons is dealt none of them, only the rares (a common slot comes empty): {gained}")
    held = from_rich([], 0, chest_full=CARDS).chest()
    check(from_rich(BUY, 490, chest_full=CARDS).chest() == held and shop.starchips() == 1000,
          "a pack whose every card the chest is full of is refused: nothing paid")
    held = from_rich([], 0, chest_full=[FIXED]).chest()
    check(from_rich(FIXED_BUY, 570, chest_full=[FIXED]).chest() == held and shop.starchips() == 1000,
          "a pack whose fixed card the chest has no room for is refused")
    check(from_rich(FIXED_BUY, 570).chest()[FIXED - 1] == 1 and shop.starchips() == 1000 - FIXED_PRICE,
          "and sold with room: the fixed card in the chest")
    game.quit()

    # Without the mod, △ does nothing on the Password screen.
    plain = Shop(executable, "plain", mods, with_mod=False)
    screen = plain.game.save("screen.state")
    plain.game.load(screen)
    still = plain.play([], 100).game.shot("still.png").read_bytes()
    plain.game.load(screen)
    plain.play([(20, "triangle")], 100)
    check(plain.game.shot("pressed.png").read_bytes() == still,
          "without a pack mod the triangle changes nothing on the screen")
    check("pack-shop" not in chunks(screen)[1], "and a state has no pack-shop chunk")
    plain.game.quit()
    print("packs: all passed")


if __name__ == "__main__":
    main()
