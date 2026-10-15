#!/usr/bin/env python3
"""Generate the built-in named image catalog without game data.

Every name a mod may put in mod.json's "assets", with the geometry the engine
reads that image by. The extractor owns the card/portrait/screen/story
layouts; the HD recipes own the frontend's 2D sprites, named here so a mod can
replace one on its own. Names contain logical palette indices, never disc
offsets. --check verifies the checked-in outputs are current.
"""
import argparse
import json
import re
from pathlib import Path
import extract_images as X

ROOT = Path(__file__).resolve().parents[2]
RECIPES = Path(__file__).resolve().parent / 'hd_recipes'

# The card panel's sprites in column 3 of every card UI package: the level
# star's palette, then the palette holding the ten ATK/DEF digits and the five
# words. hd_assets_pack.py paints these same rects (it imports them from here).
STAR_PALETTE, LABEL_PALETTE = 0x1180, 0x11E0
DIGITS = [(16 + 6 * i, 144, 6, 13) for i in range(10)]
LABELS = [(0, 158, 56, 16), (0, 174, 56, 16), (0, 190, 56, 16), (0, 206, 24, 12), (0, 218, 24, 12)]

# The frontend's 2D sprites, named from the HD recipes' "pixel" sheets: those
# rects are sprites the game blits, in the sheet's own pixels. The recipes'
# "model" and "tile" sheets are a 3D model's texture or a repeated fill, where
# a single rect means nothing on its own -- those stay whole-sheet images
# (the sheets/* names). Keyed by the recipe's own wording, with the number of
# groups and sprites each is expected to hold: a recipe that grows or is
# reordered fails the check instead of quietly renaming a modder's asset.
#
# `names` is either a slug, numbered when a group holds more than one sprite,
# or the sprites' own names in the order merge() returns them (reading order).
# "skip": the same words are already named elsewhere.
MONSTER_TYPES = ('dragon', 'spellcaster', 'zombie', 'warrior', 'beast_warrior', 'beast', 'winged_beast',
                 'fiend', 'fairy', 'insect', 'dinosaur', 'reptile', 'fish', 'sea_serpent', 'machine',
                 'thunder', 'aqua', 'pyro', 'rock', 'plant', 'magic', 'trap', 'ritual', 'equip')
# The Guardian Stars in the game's own numbering (gCard star fields, 1-10).
GUARDIAN_STARS = ('mars', 'jupiter', 'saturn', 'uranus', 'pluto', 'neptune', 'mercury', 'sun', 'moon', 'venus')
# The Build Deck sort orders, named by the mode each icon selects.
# D_80090DD8 (src/game/card_type_icon_table.c) is pairs of (icon, sort mode),
# and the icon byte is the sheet cell itself: (y / 16) << 4 | (x - 128) / 8,
# which holds for all eight. So the cell order below is the modes
# 8, 1, 2, 3, 4, 5, 6, 9, and card_list_sort.c says what each mode does:
# 1 the card number, 2 the owned ones first, 3 the better of ATK and DEF,
# 4 ATK, 5 DEF, 6 the card type, 8 the player's own order, 9 random.
SORT_ORDERS = ('your_order', 'card_number', 'owned_first', 'best_stat', 'attack', 'defense',
               'card_type', 'random')
DIGITS_0_9 = tuple(f'digit_{d}' for d in range(10))
# The turn arrow's flat frame: its cell's lower rows belong to another
# sprite, so the game draws only the eight rows the arrow is in.
FLAT_CELL = 4

RECIPE_SPRITES = {
    # The large font's glyphs, not row numbers: the capture caught whichever
    # letters the list happened to draw. The whole sheet is already
    # sheets/boot/a/column-0/palette-*, and text has its own "font" key.
    ('build_deck', 'row numbers drawn from the large font as sprites'): 'skip',
    # Generated for all 24 types below, not just the 15 the capture saw.
    ('build_deck', 'monster type icon'): 'skip',
    ('build_deck', 'guardian star symbols'):
        (tuple(f'deck_ui/guardian_star_{star}' for star in GUARDIAN_STARS), 1, 10,
         'a Guardian Star symbol on the card panel'),
    ('build_deck', 'small digits in the count boxes, ATK/DEF marks'):
        (('deck_ui/atk_mark', 'deck_ui/def_mark') + tuple(f'deck_ui/{d}' for d in DIGITS_0_9), 1, 12,
         'the ATK and DEF marks, then the count-box digits'),
    ('build_deck', 'small digits, yellow'):
        (tuple(f'deck_ui/yellow_{d}' for d in DIGITS_0_9), 1, 10, 'a small yellow digit'),
    ('build_deck', 'small digits, blue'):
        (tuple(f'deck_ui/blue_{d}' for d in DIGITS_0_9), 1, 10, 'a small blue digit'),
    ('build_deck', 'small digits, green'):
        (tuple(f'deck_ui/green_{d}' for d in DIGITS_0_9), 1, 10, 'a small green digit'),
    ('build_deck', 'small digits, grey'):
        (tuple(f'deck_ui/grey_{d}' for d in DIGITS_0_9), 1, 10, 'a small grey digit'),
    ('build_deck', 'small digits, red'):
        (tuple(f'deck_ui/red_{d}' for d in DIGITS_0_9), 1, 10, 'a small red digit'),
    ('build_deck', 'sort order icon'):
        (tuple(f'deck_ui/sort_{order}' for order in SORT_ORDERS), 8, 1, 'a Build Deck sort order icon'),
    # One group of boxes, list frames and arrows, each a piece of the screen's
    # furniture with no name of its own: numbered in reading order.
    # One group of boxes, list frames, arrows and markers. Only the two
    # labelled boxes are a thing with a name; the rest is furniture, kept at
    # the index merge() gives it rather than grouped on a guess.
    ('build_deck', 'CHEST, ORDER and DECK boxes, list frames, arrows'):
        (('deck_ui/chest_box',) + tuple(f'deck_ui/panel-{i:02d}' for i in range(1, 5))
         + ('deck_ui/order_box',) + tuple(f'deck_ui/panel-{i:02d}' for i in range(6, 15)), 1, 15,
         'a CHEST/ORDER/DECK box, list frame, arrow or marker'),
    ('build_deck', 'cursor bar'): ('deck_ui/cursor_bar', 1, 1, 'the highlighted row behind the cursor'),
    ('build_deck', 'level star'): 'skip',
    ('build_deck', 'card labels: Magic/Trap/Equip, ATK, DFD, level star'): 'skip',
    ('build_deck', 'attribute ball'): 'skip',
    # Five pieces: the word itself, then the box drawn around it.
    ('duel', 'FIELD box'):
        (('duel_ui/field_box-00', 'duel_ui/field_word') + tuple(f'duel_ui/field_box-{i:02d}' for i in range(2, 5)),
         1, 5, 'the word FIELD, or a piece of the box around it'),
    ('duel', 'life points panel (your turn)'):
        (('duel_ui/life_points_you',), 1, 1, 'the life points panel on your turn'),
    ("duel", "life points panel (opponent's turn)"):
        (('duel_ui/life_points_opponent',), 1, 1, "the life points panel on the opponent's turn"),
    # Generated on the strip's own 16x16 grid below: the capture's rects are
    # the UVs the game drew with, a pixel short of the grid from the second
    # cell on, so each one clipped a column and took a column of its neighbour.
    ('duel', 'turn arrows'): 'skip',
}


def merge(rects):
    """A recipe group records every rect the capture saw drawn, so one sprite
    can appear twice at two sizes (a 15x15 ball and the 16x16 word it sits
    in). Overlapping rects are one sprite: their bounding box."""
    boxes = [tuple(r) for r in rects]
    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
                        and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]):
                    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
                    x1 = max(a[0] + a[2], b[0] + b[2])
                    y1 = max(a[1] + a[3], b[1] + b[3])
                    boxes[i] = (x0, y0, x1 - x0, y1 - y0)
                    boxes.pop(j)
                    merged = True
                    break
            if merged:
                break
    return sorted(boxes, key=lambda r: (r[1], r[0]))   # reading order, so the names are stable


BOOT_SPRITES = Path(__file__).resolve().parent / 'boot_sprites.json'
# Hand-written names for them, kept apart so collecting the sprites again
# never overwrites the naming: {"c1-x016-y128-16x16-p64": "button_cross"}.
BOOT_NAMES = Path(__file__).resolve().parent / 'boot_names.json'
# Positional names to leave out: sprites not worth a name of their own, kept
# apart from the collected sprites for the same reason the names are.
BOOT_DELETED = Path(__file__).resolve().parent / 'boot_deleted.json'
# Column 0, the large font's atlas, is left out: text has its own key.
BOOT_COLUMNS = {1: 0xB50000, 2: 0xB58000}
BOOT_PALETTES = 0xB60000        # the block the sheet's palettes sit in


def boot_sprites(sprite, already):
    """The frontend sheet's own sprites, from what the game drew.

    sheets/boot/a columns 1 and 2 are the sheet nearly every screen cuts its
    pieces from. Where those cuts are, and which palette each is read
    through, is in tools/pc/boot_sprites.json, collected by
    tools/pc/boot_sprites.py from texture dumps -- the disc says neither.
    Column 0 of the same sheet is the large font's atlas and is left out:
    a mod replaces text with a font of its own, not a glyph at a time.

    A name starts positional, `c<column>-x<x>-y<y>-<w>x<h>-p<palette>`: the
    sheet gives no better one, and a name that says where a sprite sits can
    be renamed to what it is once somebody has looked at it. A sprite whose
    words and palette already carry a name (the monster type icons, the
    Guardian Stars, the sort icons) keeps it; only the rest are named here.

    boot_names.json does the renaming, a positional name on the left and
    what the sprite is on the right. Look at them with

        python3 tools/pc/preview_assets.py --data game/DATA \'boot_ui/*\'

    and name the ones worth naming; the rest keep where they are as a name.
    A left-hand side that matches no sprite is an error, so a name cannot
    quietly stop applying when the sprites are collected again."""
    try:
        listing = json.loads(BOOT_SPRITES.read_text())
    except (OSError, ValueError):
        return      # the dumps have not been collected in this tree
    try:
        renames = json.loads(BOOT_NAMES.read_text())
    except OSError:
        renames = {}
    if not isinstance(renames, dict):
        raise SystemExit(f'{BOOT_NAMES}: each entry is "<positional name>": "<new name>"')
    renames = {k: v for k, v in renames.items() if not k.startswith('_')}   # "_" keys are notes
    if not all(isinstance(v, str) and v for v in renames.values()):
        raise SystemExit(f'{BOOT_NAMES}: each entry is "<positional name>": "<new name>"')
    try:
        dropped = json.loads(BOOT_DELETED.read_text())
    except OSError:
        dropped = []
    if not isinstance(dropped, list) or not all(isinstance(v, str) for v in dropped):
        raise SystemExit(f'{BOOT_DELETED}: a list of positional names')
    dropped = {v for v in dropped if not v.startswith('_')}
    if dropped & set(renames):
        raise SystemExit(f'{BOOT_DELETED}: also named in {BOOT_NAMES.name}: '
                         + ', '.join(sorted(dropped & set(renames))[:5]))
    used, positional = {}, set()
    taken = {(e['offset'], e['words'], e['rows'], e['bpp'], e['clut_offset'],
              e['stride'], e['crop_left'], e['width']) for e in already}

    def placed(entry):
        """Where an entry sits on one of these columns: the column, the texels
        it spans and the palette it is read through. None if it is not a
        rectangle of one of them."""
        for column, start in BOOT_COLUMNS.items():
            if (start <= entry['offset'] < start + 256 * 64 * 2
                    and entry['stride'] == 64 and entry['bpp'] == 4):
                row, word = divmod(entry['offset'] - start, 128)
                left = word // 2 * 4 + entry['crop_left']
                return (column, left, left + entry['width'], row, row + entry['rows'],
                        entry['clut_offset'])
        return None

    # Sprites already named for what they are. A capture often sees the same
    # sprite a pixel off the sheet's grid (the game's UVs do that), so the
    # test is an overlap through the same palette, not an identical rectangle:
    # those words are reachable by the better name already.
    elsewhere = [q for q in (placed(e) for e in already
                             if not e['name'].startswith(('card_art/', 'thumbnails/', 'nameplate/')))
                 if q]
    for item in listing:
        base = BOOT_COLUMNS[item['column']]
        x, y, w, h, clut = item['x'], item['y'], item['w'], item['h'], item['clut']
        crop = x % 4
        words = -(-(crop + w) // 4)
        offset = base + y * 64 * 2 + (x // 4) * 2
        if (offset, words, h, 4, clut, 64, crop, w) in taken:
            continue        # already named for what it is
        if any(column == item['column'] and palette_of == clut
               and x < right and left < x + w and y < bottom and top < y + h
               for column, left, right, top, bottom, palette_of in elsewhere):
            continue        # the same words through the same palette, named already
        step = clut - BOOT_PALETTES
        palette = f'{step // 0x20}' if 0 <= step and not step % 0x20 else f'{clut:06x}'
        where = f"c{item['column']}-x{x:03d}-y{y:03d}-{w}x{h}-p{palette}"
        positional.add(where)
        if where in dropped:
            continue
        name = renames.get(where, where)
        if used.get(name, where) != where:
            raise SystemExit(f'{BOOT_NAMES}: {name!r} names both {used[name]} and {where}')
        used[name] = where
        sprite(f'boot_ui/{name}', X.WA, base, clut, x, y, w, h, 4,
               what=f"a sprite of the frontend sheet, drawn in {', '.join(item['seen'])}")
    stale = sorted((set(renames) | dropped) - positional)
    if stale:
        raise SystemExit(f'{BOOT_NAMES}: no sprite is called {", ".join(stale[:5])}'
                         + (f' (and {len(stale) - 5} more)' if len(stale) > 5 else ''))


def type_icons(sprite):
    """The monster type icons, through `sprite`.

    The recipes hold the fifteen the HD capture happened to draw, but the
    sheet lays all twenty-four out by type: cell (128 + (type % 8) * 16,
    (type // 8) * 16), palette 16 + type. Every one of the fifteen agrees
    with that, and the nine the capture missed are the right pictures at the
    cells it predicts, so they are generated rather than captured."""
    recipe = json.loads((RECIPES / 'build_deck.json').read_text())
    groups = [s for s in recipe['sheets'] if s['what'] == 'monster type icon']
    if not groups:
        raise SystemExit('build_deck.json: no "monster type icon" sheet to take the layout from')
    first = min(groups, key=lambda s: int(s['palette'], 16))
    sheet, palette, bpp = int(first['offset'], 16), int(first['palette'], 16), first['bpp']
    if tuple(first['rects'][0]) != (128, 0, 16, 16):
        raise SystemExit(f'build_deck.json: the first monster type icon is at {first["rects"][0]}, not (128, 0, 16, 16)')
    for index, kind in enumerate(MONSTER_TYPES):
        sprite(f'deck_ui/type_{kind}', first['archive'], sheet, palette + index * 0x20,
               128 + (index % 8) * 16, (index // 8) * 16, 16, 16, bpp,
               what=f'the {kind.replace("_", "-")} type icon')


def turn_arrows(sprite):
    """The turn arrow's strip, through `sprite`.

    Eight 16x16 cells in a row at (0, 144). The recipe holds the rects the
    HD capture saw the game draw, and those run 0, 15, 31, 47, ... : a pixel
    short of the grid from the second cell on, so each rect lost its own last
    column and took one of its neighbour's (the yellow edge that showed up in
    the sixth). The grid is what the sheet actually holds, so the cells are
    generated from it rather than captured.

    Every cell is sixteen wide. All but the flat middle one are sixteen tall
    too; that one is eight, which is what the game draws there and the only
    height that holds the arrow alone. Its sixteen rows are shared: another
    sprite sits above it (rows 136-143) and a yellow bordered box below it
    (rows 152-159, through this palette), with the arrow a single red line at
    row 151. Taken as sixteen rows the frame would carry that yellow box, so
    it is taken as the eight rows 144-151, which the game uses and which hold
    nothing but the arrow."""
    recipe = json.loads((RECIPES / 'duel.json').read_text())
    strip = next((s for s in recipe['sheets'] if s['what'] == 'turn arrows'), None)
    if strip is None:
        raise SystemExit('duel.json: no "turn arrows" sheet to take the layout from')
    top = min(y for _, y, _, _ in strip['rects'])
    for cell in range(8):
        sprite(f'duel_ui/turn_arrow-{cell:02d}', strip['archive'], int(strip['offset'], 16),
               int(strip['palette'], 16), cell * 16, top, 16, 8 if cell == FLAT_CELL else 16,
               strip['bpp'], what="a frame of the turn arrow's spin")


def recipe_sprites(sprite):
    """Every named sprite the HD recipes describe, through `sprite`."""
    for recipe in ('build_deck', 'duel'):
        sheets = json.loads((RECIPES / f'{recipe}.json').read_text())['sheets']
        groups, seen = [s for s in sheets if s.get('method') == 'pixel'], {}
        for sheet in groups:
            key = (recipe, sheet['what'])
            if key not in RECIPE_SPRITES:
                raise SystemExit(f'{recipe}.json: no name for the "{sheet["what"]}" sprites; '
                                 'add it to RECIPE_SPRITES')
            seen.setdefault(key, []).append(sheet)
        for key, found in seen.items():
            entry = RECIPE_SPRITES[key]
            if entry == 'skip':
                continue
            slug, want_groups, want_sprites, what = entry
            if not isinstance(slug, str) and len(slug) != want_groups * want_sprites:
                raise SystemExit(f'{key[0]}.json: "{key[1]}" needs {want_groups * want_sprites} names, '
                                 f'{len(slug)} given')
            if len(found) != want_groups:
                raise SystemExit(f'{key[0]}.json: "{key[1]}" has {len(found)} groups, '
                                 f'{slug} expects {want_groups}')
            for g, sheet in enumerate(found):
                boxes = merge(sheet['rects'])
                if len(boxes) != want_sprites:
                    raise SystemExit(f'{key[0]}.json: "{key[1]}" group {g} holds {len(boxes)} '
                                     f'sprites, {slug} expects {want_sprites}')
                for i, (x, y, w, h) in enumerate(boxes):
                    if isinstance(slug, str):
                        name = slug
                        if want_groups > 1:
                            name += f'-{g:02d}'
                        if want_sprites > 1:
                            name += f'-{i:02d}'
                    else:
                        name = slug[g * want_sprites + i]
                    sprite(name, sheet['archive'], int(sheet['offset'], 16), int(sheet['palette'], 16),
                           x, y, w, h, sheet['bpp'], what=what)


# Moves of your own, on top of the rules below: tools/pc/categories.json.
CATEGORIES = Path(__file__).resolve().parent / 'categories.json'
_moves, _moved, _targets = None, set(), {}


def moves() -> dict:
    """{what to move: where to}. A key that is an asset's whole name moves
    that one; any other key is a start, and everything beginning with it
    moves, that much of the name replaced. Keys starting with "_" are notes."""
    global _moves
    if _moves is None:
        try:
            table = json.loads(CATEGORIES.read_text())
        except OSError:
            table = {}
        if not isinstance(table, dict) or not all(isinstance(v, str) and v for k, v in table.items()
                                                  if not k.startswith('_')):
            raise SystemExit(f'{CATEGORIES}: each entry is "<name or folder/>": "<where to>"')
        _moves = {k: v for k, v in table.items() if not k.startswith('_')}
    return _moves


def move(name: str) -> str:
    """`name` after the moves: a whole name first, then the longest start
    that matches, so a narrower move wins over a wider one."""
    table = moves()
    if name in table:
        _moved.add(name)
        return table[name]
    for key in sorted(table, key=len, reverse=True):
        if name.startswith(key):
            _moved.add(key)
            return table[key] + name[len(key):]
    return name


# The catalog's folders are the parts a mod thinks in, not the shapes the
# disc keeps them in: a card's picture, its thumbnail and its name plate sit
# in one record but are three different things to replace.
def recategorise(name: str) -> str:
    family, _, rest = name.partition('/')
    if family == 'cards':
        # Three digits, 001 to 722: the extractor numbers a card in four, but
        # a card's number never passes 722 and the folders read better short.
        if rest.endswith('.small'):
            return f'thumbnails/{int(rest[:-len(".small")]):03d}'
        if rest.endswith('.strip'):
            return f'nameplate/{int(rest[:-len(".strip")]):03d}'
        return f'card_art/{int(rest):03d}'
    if family == 'card_ui':      # the card panel: frames, back, star, digits, words
        if rest.startswith('attribute_'):
            return f'attributes/{rest[len("attribute_"):]}'
        return f'card_frames/{rest}'
    if family == 'deck_ui':      # the Build Deck and Trade screens
        if rest.startswith('guardian_star_'):
            return f'star_guardians/{rest[len("guardian_star_"):]}'
        if rest.startswith('type_'):
            return f'monster_type/{rest[len("type_"):]}'
        return f'build_deck/{rest}'
    if family == 'duel_ui':
        return f'duel/{rest}'
    if family == 'boot_ui':      # the sheet nearly every screen draws from
        return f'UI/{rest}'
    return name


def categorised(name: str) -> str:
    """The folder a name ends up in. Two different assets landing on one name
    would make one of them unreachable, so that is an error, not a merge --
    unlike one asset the disc repeats, which keeps its single name."""
    after = move(recategorise(name))
    if _targets.setdefault(after, name) != name:
        raise SystemExit(f'{CATEGORIES}: {after!r} would be both {_targets[after]!r} and {name!r}')
    return after


def catalog():
    result = []
    _moved.clear()
    _targets.clear()

    def add(name, archive, offset, words, rows, bpp, clut, entries=None, stride=None, crop=0, width=None,
            what=''):
        result.append(dict(name=categorised(name), archive=archive, offset=offset, words=words, rows=rows, bpp=bpp,
                           clut_offset=clut or 0, clut_entries=entries if entries is not None else {4:16, 8:256, 16:0}[bpp],
                           stride=stride or words, crop_left=crop, width=width or words * (16 // bpp), what=what))

    def sprite(name, archive, sheet, clut, x, y, w, h, bpp, stride=64, what=''):
        """One sprite inside a sheet: the words its rows cover, cropped to the
        rect. The loader leaves the texels outside the crop to the disc, so a
        neighbouring sprite sharing an edge word survives the replacement."""
        per = 16 // bpp
        crop = x % per
        add(name, archive, sheet + y * stride * 2 + (x // per) * 2,
            -(-(crop + w) // per), h, bpp, clut, stride=stride, crop=crop, width=w, what=what)

    class Collector(X.Extractor):
        def image(self, archive, offset, words, rows, bpp, clut_offset, path, alias, clut_entries=None, **kw):
            name = path.removesuffix('.png')
            # cards/NNNN.side is not a picture: those 1408 bytes are the card
            # record's second copy of the 40x32 thumbnail followed by its
            # 64-color palette, which extract_images.py reads as a 16x88
            # image through the art's 256-color palette instead, so it comes
            # out as noise. There is nothing there for a mod to replace.
            if name.endswith('.side'):
                return
            # Portraits and the story's scenes are not named: a mod that wants
            # them uses a texture pack, which can address any words at all.
            if name.startswith(('portraits/', 'scenes/')):
                return
            add(name, archive, offset, words, rows, bpp, clut_offset, clut_entries, what=alias)

    # Only the cards are walked now: the portraits and the story's scenes are
    # filtered out above, and the screens' sheets are not named at all
    # (sheet_columns below keeps their layout for the tools).
    ex = Collector('', '')
    ex.cards({})

    recipe_sprites(sprite)
    type_icons(sprite)
    turn_arrows(sprite)
    boot_sprites(sprite, result)

    # Repeated card UI packages: one named asset replaces every retail copy.
    packages = [(0x10C4800, 0x10E8800), (0xEE6800, 0xF06800), (0xF97800, 0xFB7800)]
    packages += [(0xB63000 + i * 0xEB * X.SECTOR, 0xB63000 + i * 0xEB * X.SECTOR + 64 * X.SECTOR)
                 for i in range(7)]
    for base, palette in packages:
        # Six palettes of the one frame sheet: the four kinds, then the two
        # extra colorings the game also draws it in.
        for row, frame in enumerate(('monster', 'magic', 'trap', 'ritual', 'purple', 'orange'), 8):
            for column in range(2):
                add(f'card_ui/frame_{frame}/column-{column}', X.WA, base + column * X.COLUMN,
                    64, 256, 8, palette + row * 0x200, what=f'the {frame} card frame')
            # Column 2 carries the back's foot, read through the same palette
            # as the frame it is turned over beside.
            add(f'card_ui/card_back/{frame}', X.WA, base + 2 * X.COLUMN,
                64, 256, 8, palette + row * 0x200, what=f'the card back, beside the {frame} frame')
        column3 = base + 3 * X.COLUMN
        for i, attribute in enumerate(('light', 'dark', 'earth', 'water', 'fire', 'wind', 'magic', 'trap')):
            sprite(f'card_ui/attribute_{attribute}', X.WA, column3, palette + 15 * 0x200 + i * 0x20,
                   16 * i, 128, 16, 16, 4, what=f'the {attribute} attribute ball')
        sprite('card_ui/level_star', X.WA, column3, palette + STAR_PALETTE, 0, 144, 9, 9, 4,
               what='the level star on the card panel')
        # The card view's numbers and words, subtracted from the frame: one
        # palette holds the ten digits and the five labels (hd_assets_pack.py).
        for i, (x, y, w, h) in enumerate(DIGITS):
            sprite(f'card_ui/digit_{i}', X.WA, column3, palette + LABEL_PALETTE, x, y, w, h, 4,
                   what=f'the digit {i} in ATK and DEF')
        for (x, y, w, h), label in zip(LABELS, ('normal_magic', 'trap', 'equip_magic', 'atk', 'def')):
            sprite(f'card_ui/label_{label}', X.WA, column3, palette + LABEL_PALETTE, x, y, w, h, 4,
                   what=f'the {label.replace("_", " ")} label on the card panel')
    return result


class Extractor(X.Extractor):
    """The extractor with its image() silenced: sheet_columns only wants the
    sheets it discovers, not the pictures it would write."""
    def image(self, *arguments, **named):
        pass


def sheet_columns():
    """The screens' sheet columns and the readings each is made through.

    The catalog does not name these: a column is not a picture a mod would
    replace, it is a slab many sprites share, and each of its palettes is the
    key to a different set of them. tools/pc/sheet_coverage.py still needs the
    layout to show what a capture has found, so it lives here."""
    ex = Extractor('', '')
    ex.sheets_family()
    ex.scenes_family()
    out = []
    for sheet in ex.sheets:
        for column in range((sheet.sectors + 15) // 16):
            for palette, (bpp, clut) in enumerate(sheet.column_variants(column)):
                out.append({'name': f'{sheet.stem}/column-{column}/palette-{palette}',
                            'archive': sheet.archive, 'offset': sheet.base + column * X.COLUMN,
                            'words': 64, 'rows': min(16, sheet.sectors - column * 16) * 16,
                            'bpp': bpp, 'clut_offset': clut or 0,
                            'clut_entries': {4: 16, 8: 256, 16: 0}[bpp],
                            'stride': 64, 'crop_left': 0, 'width': 64 * (16 // bpp), 'what': ''})
    return out


def check_moves():
    """A move that matched nothing is a typo, not a no-op."""
    stale = sorted(set(moves()) - _moved)
    if stale:
        raise SystemExit(f'{CATEGORIES}: nothing to move for {", ".join(stale[:5])}'
                         + (f' (and {len(stale) - 5} more)' if len(stale) > 5 else ''))


def outputs():
    entries = catalog()
    check_moves()
    header = '/* Generated by tools/pc/asset_catalog.py; do not edit. */\n'
    header += 'static const AssetSpec asset_specs[] = {\n'
    fields = ('name', 'archive', 'offset', 'words', 'rows', 'bpp', 'clut_offset', 'clut_entries', 'stride', 'crop_left', 'width')
    for entry in entries:
        header += '    {' + ', '.join(json.dumps(entry[k]) for k in fields) + '},\n'
    header += '};\n'
    return {ROOT / 'src/pc/render/asset_catalog.inc': header,
            ROOT / 'docs/asset-catalog.json': '[\n' + ',\n'.join(json.dumps(entry) for entry in entries) + '\n]\n'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for path, content in outputs().items():
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f'Out of date: {path}')
        else:
            path.write_text(content)


if __name__ == '__main__':
    main()
