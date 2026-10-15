"""The duel's screen as it opens, for the UI tab's Duel page (ui_duel.py):
the board, the hand and the card bar's words drawn as the game draws them
at its 320 x 240, under the pictures a mod's "ui" changes, so those sit
exactly where they do in the game.

* The board (board_backdrop): board_model.py's render of the duel's 3D
  board from its starting camera, with the mod's textures.
* The hand (hand_card): each card a 52 x 60 frame (page (896, 256), 8 bits,
  u 0, v 128) through its frame's palette (row 241 + the frame, as
  gamedata.FRAME_NAMES counts them), the card's 40 x 32 thumbnail 6 in, and
  a monster's ATK and DEF (8 x 8 digits, u 8 d, v 88, a blank at u 80,
  four right to left from 14 in, rows 40 and 48 down) beside the sword
  and shield (8 x 16 at u 120, v 112), or the word of its kind (32 x 16 at
  u 32 k, v 96, 10 in and 40 down: Magic, Equip, Trap, Ritual); 60 apart
  from (14, 146) (func_800235C0).
* The card bar's words (bar_words): the card the cursor is on, its name in
  the 8 x 12 letters (16, 212), 8 apart; a monster's sword and shield
  (page (704, 0), u 208 and 216, v 88, palette (656, 250)) at (211, 210)
  and (211, 218) with its ATK and DEF (u 128 + 8 d, v 112) from x 219, its
  kind's icon at (253, 210) and its guardian stars' at (271, 210) and
  (289, 210); another card's kind icon and word (its frame's palette) at
  (253, 210) and (271, 210). A mod's "card_bar" parts (ui_rules.PARTS)
  move, color, hide and spread them as duel_ui.c does."""
from __future__ import annotations

import struct

from . import art, board_model, card_text, gamedata, map_view, pngio, ui_assets as ua, ui_rules

TERRAIN = "normal"

HAND_AT = [(14 + 60 * i, 146) for i in range(5)]
HAND_FRAME = (896, 256, 8, 0, 128, 52, 60)
HAND_CLUT = (256, 241)
THUMB_AT = (6, 6)
CARD_DIGIT = (0, 88)
BLANK = 10
SWORD_SHIELD = (120, 112, 8, 16)
KIND_WORD = {gamedata.TYPE_MAGIC: 0, gamedata.TYPE_EQUIP: 1, gamedata.TYPE_TRAP: 2, gamedata.TYPE_RITUAL: 3}
BAR_PAGE = (704, 0, 4, 656, 250)
BAR_NAME_AT = (16, 212)
BAR_STATS_X, BAR_ICON_X, BAR_STAR_X, BAR_Y = 219, 253, (271, 289), 210


def board_backdrop(project, size=(320, 240)) -> pngio.Image:
    """The board as the duel opens on it (board_model.render_board: the
    duel's starting camera, the mod's textures), at the game's 320 x 240
    or `size`; black without the disc."""
    try:
        image = board_model.render_board(project, TERRAIN, None, size) if project is not None else None
    except (map_view.ModelError, ValueError, IndexError, struct.error):
        image = None            # game files without the board's model where the disc has it
    if image is None:
        image = pngio.Image(size[0], size[1], bytes((0, 0, 0, 255)) * (size[0] * size[1]))
    return image


# --- the hand and the card bar's words ------------------------------------------------

def _card(project, cid):
    cards = getattr(project, "cards", None) or {}
    return cards.get(cid)


def _thumbnail(project, wa, cid):
    try:
        image = art.in_game(project, wa, cid, "thumbnail") if wa else None
    except (OSError, pngio.PngError, KeyError, ValueError):
        image = None
    if image is None and wa:
        try:
            image = art.disc_image(wa, cid, "thumbnail")
        except (OSError, ValueError, IndexError):
            image = None
    if image is not None and image.size != (40, 32):
        image = pngio.scale_to(image, 40, 32)
    return image


def _digits(vram, value: int, page, clut, at_u, at_v, count=4):
    """`value` right to left in `count` 8 x 8 digits (blank before it)."""
    text = str(max(0, value))[-count:].rjust(count)
    return [vram.sprite(*page, *clut, at_u + 8 * (BLANK if c == " " else int(c)), at_v, 8, 8) for c in text]


def hand_card(project, wa, duel: ua.DuelArt, cid: int) -> pngio.Image:
    """A card in the hand, 52 x 60, as the game draws it."""
    card = _card(project, cid)
    page_x, page_y, bits, u, v, w, h = HAND_FRAME
    frame = card.shown_frame() if card is not None else 0
    out = duel.vram.sprite(page_x, page_y, bits, HAND_CLUT[0], HAND_CLUT[1] + frame, u, v, w, h)
    thumb = _thumbnail(project, wa, cid)
    if thumb is not None:
        out = ua.paste(out, thumb, *THUMB_AT)
    page, clut = (page_x, page_y, bits), HAND_CLUT
    if card is None or card.is_monster():
        su, sv, sw, sh = SWORD_SHIELD
        out = ua.paste(out, duel.vram.sprite(*page, *clut, su, sv, sw, sh), 5, 40)
        for row, value in ((40, card.attack if card else 0), (48, card.defense if card else 0)):
            for i, digit in enumerate(_digits(duel.vram, value, page, clut, *CARD_DIGIT)):
                out = ua.paste(out, digit, 14 + 8 * i, row)
    else:
        word = KIND_WORD.get(card.type, 0)
        out = ua.paste(out, duel.vram.sprite(*page, *clut, 32 * word, 96, 32, 16), 10, 40)
    return out


def _icon(font, n):
    icon = font.icon(n) if font is not None else None
    return pngio.Image(*icon) if icon else None


def bar_words(project, wa, duel: ua.DuelArt, font, cid: int, card_bar=None) -> list:
    """What the game draws over the card bar for the card the cursor is on:
    (picture, x, y, part) each, part one of ui_rules.PARTS; with a mod's
    "card_bar", its parts moved, colored, hidden and the name's letters
    spread as duel_ui.c draws them."""
    card = _card(project, cid)
    if card is None:
        return []
    out = []
    if font is not None:
        x, y = BAR_NAME_AT
        ink = font.colors
        # At most 24 letters of a monster's name, 28 of another card's (the
        # strings' F8 07); a letter's place counts the spaces too.
        for index, c in enumerate(card.name[:24 if card.is_monster() else 28]):
            cell = font.cell(c) if c != " " else None
            if cell:
                rgba = bytearray()
                for color_index in cell:
                    color = ink[color_index]
                    rgba += bytes((*color, 255)) if color_index and color else b"\0\0\0\0"
                out.append((pngio.Image(card_text.CELL_W, card_text.CELL_H, bytes(rgba)), x + 8 * index, y, "name",
                            index))
    page, clut = BAR_PAGE[:3], BAR_PAGE[3:]
    if card.is_monster():
        out.append((duel.vram.sprite(*page, *clut, 208, 88, 8, 8), BAR_STATS_X - 8, BAR_Y, "atk", 0))
        out.append((duel.vram.sprite(*page, *clut, 216, 88, 8, 8), BAR_STATS_X - 8, BAR_Y + 8, "def", 0))
        for row, value, part in ((0, card.attack, "atk"), (8, card.defense, "def")):
            text = str(max(0, value))[-4:].rjust(4)
            for i, c in enumerate(text):
                if c != " ":
                    out.append((duel.vram.sprite(*page, *clut, 128 + 8 * int(c), 112, 8, 8),
                                BAR_STATS_X + 8 * i, BAR_Y + row, part, 0))
        icons = [(card.type, "type")] + [(card_text.ICON_NAMES.index(gamedata.STAR_NAMES[s]), "stars")
                                         for s in (card.star1, card.star2) if 0 < s < len(gamedata.STAR_NAMES)]
        for (n, part), x in zip(icons, (BAR_ICON_X,) + BAR_STAR_X):
            icon = _icon(font, n)
            if icon is not None:
                out.append((icon, x, BAR_Y, part, 0))
    else:
        icon = _icon(font, card.type)
        if icon is not None:
            out.append((icon, BAR_ICON_X, BAR_Y, "type", 0))
        word = KIND_WORD.get(card.type, 0)
        out.append((duel.vram.sprite(*HAND_FRAME[:3], HAND_CLUT[0], HAND_CLUT[1] + card.shown_frame(), 32 * word,
                                     96, 32, 16), BAR_STAR_X[0], BAR_Y, "kind", 0))
    parts = ui_rules.bar_parts(card_bar)
    drawn = []
    for picture, x, y, part, letter in out:
        element = parts.get(part)
        if element is None:
            drawn.append((picture, x, y, part))
            continue
        if element.get("hide") is True:
            continue
        dx, dy = ui_rules.part_offset(part, element)
        spacing = ui_rules.part_spacing(element) if part == "name" else 0
        drawn.append((ua.tint(picture, ua.parse_color(element.get("tint"))), x + dx + spacing * letter, y + dy, part))
    return drawn
