"""Free Duel portraits: the disc's forty, and the one the game makes of a
mod's PNG.

A portrait record is 48x48 at one byte a pixel, then a 64-entry palette of
15-bit colors: 0x980 bytes, the forty of them one after another in
WA_MRG.MRG from 0xF55000 (src/pc/cards/art.h, PORTRAIT_RECORD; ygomods.py
addresses them the same way for a texture pack).

A mod's own picture (notes/more-duelists.md, "One file, two pictures") is
made into such a record by CardArt_PortraitFromImage (src/pc/cards/art.c):
the PNG over black, its middle square averaged down to 48x48, and median cut
to 63 colors from palette entry 1. A PNG bigger than 48x48 is registered
with the texture pack as well (duelists.c register_art), and a pack's image
stands in for the record's texels at every scale: at View > Internal 1x its
middle square averaged to 48x48 in the console's 15-bit color (not the 64
colors of the record), at 2x and above the PNG at its own resolution. A
PNG of 48x48 or less is the record. in_game() below is each of those,
worked out the same way, so the editor shows what the game will: checked
against the game's own frames by tests/pc/editor_duelists_runtime.py.
"""
from __future__ import annotations

from . import pngio
from .pngio import Image

BASE = 0xF55000             # the first record in WA_MRG.MRG
RECORD = 0x980              # bytes a record: the picture, then its palette
SIDE = 48                   # PORTRAIT_SIDE
PIXELS = SIDE * SIDE        # PORTRAIT_PIXELS: the palette follows them
COLORS = 63                # the median cut's, from entry 1 (entry 0 is black)
COUNT = 40                  # Deck Build and the disc's thirty-nine


def color(word: int) -> bytes:
    """A 15-bit word as RGBA, as the screen shows it (art._color, but 0 too
    is drawn: the grid's portraits have no transparent color)."""
    r, g, b = word & 0x1F, (word >> 5) & 0x1F, (word >> 10) & 0x1F
    return bytes((r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2, 255))


def record_image(record: bytes) -> Image:
    """A portrait record as the picture it draws: 48x48."""
    palette = [color(record[PIXELS + i * 2] | record[PIXELS + i * 2 + 1] << 8) for i in range(64)]
    palette += [b"\x00\x00\x00\xff"] * (256 - 64)      # an index past the palette reads black
    return Image(SIDE, SIDE, b"".join(palette[i] for i in record[:PIXELS]))


def disc_record(wa: bytes, d: int) -> bytes:
    """Duelist d's record as the disc has it (0 is Deck Build's)."""
    if not 0 <= d < COUNT:
        raise ValueError(f"duelist {d} has no portrait on the disc")
    start = BASE + d * RECORD
    record = bytes(wa[start:start + RECORD])
    return record if len(record) == RECORD else bytes(RECORD)


def disc_portrait(wa: bytes, d: int) -> Image:
    return record_image(disc_record(wa, d))


# --- a PNG made into a record, as art.c makes it ------------------------------

def _over_black(image: Image) -> bytes:
    """RGB, each channel times its alpha over 255, rounded down: load_png."""
    if image.opaque():
        rgba = image.rgba
        out = bytearray(len(rgba) // 4 * 3)
        for c in range(3):
            out[c::3] = rgba[c::4]
        return bytes(out)
    out = bytearray(image.width * image.height * 3)
    alpha = image.rgba[3::4]
    for c in range(3):
        out[c::3] = bytes(v * a // 255 for v, a in zip(image.rgba[c::4], alpha))
    return bytes(out)


def _resample(rgb: bytes, sw: int, sh: int, w: int, h: int) -> list:
    """art.c resample: `w` x `h` from the middle of the picture at that shape,
    each pixel the average (rounded down) of the source pixels under it.
    [(r, g, b)] row by row."""
    cw, ch = float(sw), float(sh)
    if cw * h > ch * w:
        cw = ch * w / h
    else:
        ch = cw * h / w
    x0, y0 = (sw - cw) / 2, (sh - ch) / 2
    columns = []
    for x in range(w):
        left, right = int(x0 + cw * x / w), int(x0 + cw * (x + 1) / w)
        if right <= left:
            right = left + 1
        columns.append((left, min(right, sw)))
    out = []
    for y in range(h):
        top, bottom = int(y0 + ch * y / h), int(y0 + ch * (y + 1) / h)
        if bottom <= top:
            bottom = top + 1
        rows = [rgb[sy * sw * 3:(sy + 1) * sw * 3] for sy in range(top, min(bottom, sh))]
        for left, right in columns:
            n = len(rows) * max(0, right - left) or 1
            r = sum(sum(row[left * 3:right * 3:3]) for row in rows)
            g = sum(sum(row[left * 3 + 1:right * 3:3]) for row in rows)
            b = sum(sum(row[left * 3 + 2:right * 3:3]) for row in rows)
            out.append((r // n, g // n, b // n))
    return out


def _to555(r: int, g: int, b: int) -> int:
    word = (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)
    return word or 0x8000       # 0 is the transparent color; this is black


def _quantize(pixels: list, colors: int):
    """art.c quantize: median cut to `colors` entries, written from entry 1
    (entry 0 and those left over 0x8000); each pixel the nearest entry by
    3:4:2 weighted distance, the lower entry between equals. (clut, indices)."""
    ordered = list(pixels)
    boxes = [[0, len(ordered)]]
    while len(boxes) < colors:
        best, best_range, axis = -1, 0, 0
        for i, (first, count) in enumerate(boxes):
            if count < 2:
                continue
            part = ordered[first:first + count]
            for a in range(3):
                values = [p[a] for p in part]
                spread = max(values) - min(values)
                if spread > best_range:         # the first box and axis win a tie, as in art.c
                    best_range, best, axis = spread, i, a
        if best < 0 or best_range < 4:
            break
        first, count = boxes[best]
        # By one channel, then all three: a whole order, so the split is the
        # same whichever way the equal pixels came (art.c by_axis).
        ordered[first:first + count] = sorted(ordered[first:first + count], key=lambda p: (p[axis], p))
        half = count // 2
        boxes.append([first + half, count - half])
        boxes[best][1] = half
    palette = []
    clut = [0x8000] * (colors + 1)
    for i, (first, count) in enumerate(boxes):
        part = ordered[first:first + count]
        n = count or 1
        entry = tuple(sum(p[a] for p in part) // n for a in range(3))
        palette.append(entry)
        clut[i + 1] = _to555(*entry)
    nearest = {}
    indices = bytearray(len(pixels))
    for k, (r, g, b) in enumerate(pixels):
        index = nearest.get((r, g, b))
        if index is None:
            best_distance = -1
            for i, (pr, pg, pb) in enumerate(palette):
                distance = (r - pr) ** 2 * 3 + (g - pg) ** 2 * 4 + (b - pb) ** 2 * 2
                if best_distance < 0 or distance < best_distance:
                    best_distance, index = distance, i
            index += 1
            nearest[(r, g, b)] = index
        indices[k] = index
    return clut, bytes(indices)


def record_from(image: Image) -> bytes:
    """CardArt_PortraitFromImage: the record the game makes of a PNG."""
    rgb = _over_black(image)
    pixels = _resample(rgb, image.width, image.height, SIDE, SIDE)
    clut, indices = _quantize(pixels, COLORS)
    palette = b"".join(word.to_bytes(2, "little") for word in clut)
    return indices + palette


def crop(image: Image):
    """CardArt_Crop at 48:48: the middle square the game draws at Internal 2x
    and above, in whole pixels (left, top, width, height)."""
    fw, fh = float(image.width), float(image.height)
    if fw * SIDE > fh * SIDE:
        fw = fh
    else:
        fh = fw
    cw, ch = max(1, int(fw + 0.5)), max(1, int(fh + 0.5))
    return int((image.width - cw) / 2 + 0.5), int((image.height - ch) / 2 + 0.5), cw, ch


def sharp(image: Image) -> bool:
    """Whether the game draws the PNG itself above 1x: only a picture bigger
    than the console's 48x48 has more to show (duelists.c register_art)."""
    _, _, cw, ch = crop(image)
    return cw > SIDE or ch > SIDE


def hd_image(image: Image) -> Image:
    """The picture the game draws at Internal 2x and above: the middle square
    of the PNG, over black (the slot has no alpha)."""
    left, top, w, h = crop(image)
    return pngio.flatten(pngio.crop(image, left, top, w, h))


def pack_texels(image: Image) -> Image:
    """The 48x48 the texture pack paints over the record's texels from the
    PNG's middle square (texture_pack.c load_pixels, a made image): over
    black, each texel the average of the pixels in its whole-pixel box,
    rounded down, at 5 bits a channel. A texel that comes out 0 or 1 is
    the pack's opaque black, which the renderer draws from the game's own
    texel (soft_gpu.c): black where the record's color there is black
    (0x8000, with the bit), the darkest red (0x0001) where it is not."""
    record = record_from(image)
    clut = [record[PIXELS + 2 * i] | record[PIXELS + 2 * i + 1] << 8 for i in range(64)]
    left, top, w, h = crop(image)
    rgb = _over_black(pngio.crop(image, left, top, w, h))
    out = bytearray()
    for y in range(SIDE):
        y0, y1 = y * h // SIDE, (y + 1) * h // SIDE
        y1 = max(y1, y0 + 1)
        rows = [rgb[sy * w * 3:(sy + 1) * w * 3] for sy in range(y0, min(y1, h))]
        for x in range(SIDE):
            x0, x1 = x * w // SIDE, (x + 1) * w // SIDE
            x1 = min(max(x1, x0 + 1), w)
            n = len(rows) * (x1 - x0) or 1
            word = 0
            for channel in range(3):
                total = sum(sum(row[x0 * 3 + channel:x1 * 3:3]) for row in rows)
                word |= ((total // n) >> 3) << (5 * channel)
            if word <= 1:       # TEXTURE_SHADOW_BLACK
                word = 0x8000 if clut[record[y * SIDE + x] & 63] & 0x8000 else 0x0001
            out += color(word)
    return Image(SIDE, SIDE, bytes(out))


def in_game(image: Image, scale: int = 1) -> Image:
    """The portrait at View > Internal `scale`x. A PNG bigger than 48x48:
    its middle square averaged to 48x48 at 15 bits a pixel at 1x (the pack's
    image painted over the record, texture_pack.c), drawn at 48 * scale
    above it. One of 48x48 or less: the 64-color record, at any scale."""
    if sharp(image):
        if scale > 1:
            return pngio.resample(hd_image(image), SIDE * scale, SIDE * scale)
        return pack_texels(image)
    return pngio.scale_nearest(record_image(record_from(image)), scale)


def thumbnail(image: Image, size: int) -> Image:
    """A small copy for a list, `size` pixels square: averaged down (or
    grown by whole pixels from a 48x48 record, which stays sharp)."""
    if image.width <= size and image.height <= size and size % image.width == 0 and image.width == image.height:
        return pngio.scale_nearest(image, size // image.width)
    box = pngio.middle(image, size, size)
    if box[2] >= size:
        return pngio.flatten(pngio.resample(image, size, size, box))
    return pngio.scale_to(pngio.flatten(pngio.crop(image, round(box[0]), round(box[1]), round(box[2]),
                                                  round(box[3]))), size, size)
