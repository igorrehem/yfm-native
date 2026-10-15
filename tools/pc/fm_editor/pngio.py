"""PNG in and out, and the few image operations the Art tab needs, in plain
Python: the editor needs nothing beyond Python and Tkinter.

An image here is (width, height, rgba): rgba is bytes, four per pixel, rows
top to bottom.
"""
from __future__ import annotations

import hashlib
import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PngError(Exception):
    pass


class Image:
    """Never changed once made: a copy is the image itself, so the undo
    history's snapshots share one picture rather than storing it each time."""
    __slots__ = ("width", "height", "rgba", "_digest")

    def __init__(self, width: int, height: int, rgba: bytes):
        if len(rgba) != width * height * 4:
            raise ValueError("pixels do not match the size")
        self.width, self.height, self.rgba = width, height, bytes(rgba)

    @property
    def size(self):
        return self.width, self.height

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self

    def digest(self) -> bytes:
        """SHA-256 of its size and pixels, worked out once."""
        try:
            return self._digest
        except AttributeError:
            h = hashlib.sha256(struct.pack("<II", self.width, self.height))
            h.update(self.rgba)
            self._digest = h.digest()
            return self._digest

    def __eq__(self, other):
        return isinstance(other, Image) and self.size == other.size and self.rgba == other.rgba

    def pixel(self, x: int, y: int):
        at = (y * self.width + x) * 4
        return tuple(self.rgba[at:at + 4])

    def opaque(self) -> bool:
        return self.rgba[3::4] == b"\xff" * (self.width * self.height)


def _rgb(rgba: bytes) -> bytes:
    """RGBA bytes without the alpha."""
    out = bytearray(len(rgba) // 4 * 3)
    for c in range(3):
        out[c::3] = rgba[c::4]
    return bytes(out)


# --- reading --------------------------------------------------------------------

def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _unfilter(data: bytes, width: int, height: int, bits: int, channels: int, start: int = 0):
    """The rows of one (sub)image, filters undone; (rows, next offset)."""
    bpp = max(1, bits * channels // 8)
    stride = (width * bits * channels + 7) // 8
    rows, previous, at = [], bytearray(stride), start
    for _ in range(height):
        if at >= len(data):
            raise PngError("the image data ends early")
        kind = data[at]
        line = bytearray(data[at + 1:at + 1 + stride])
        if len(line) != stride:
            raise PngError("the image data ends early")
        at += 1 + stride
        if kind == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif kind == 2:
            line = bytearray((x + y) & 0xFF for x, y in zip(line, previous))
        elif kind == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + previous[i]) >> 1)) & 0xFF
        elif kind == 4:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                upper_left = previous[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(left, previous[i], upper_left)) & 0xFF
        elif kind != 0:
            raise PngError(f"unknown row filter {kind}")
        rows.append(line)
        previous = line
    return rows, at


def _samples(line: bytes, width: int, bits: int, channels: int):
    """A row's samples as 8-bit values (16-bit ones keep their high byte;
    sub-byte ones are left as indices or scaled grey by the caller)."""
    count = width * channels
    if bits == 8:
        return list(line[:count])
    if bits == 16:
        return list(line[0:count * 2:2])
    out = []
    per = 8 // bits
    mask = (1 << bits) - 1
    for i in range(count):
        byte = line[i // per]
        out.append((byte >> (8 - bits - (i % per) * bits)) & mask)
    return out


# The depths each color type may have (the PNG spec, table 11.1).
DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}


def decode(data: bytes) -> Image:
    """A PNG file's bytes as RGBA: every color type and depth, tRNS,
    interlaced or not. A damaged file is a PngError, as libpng refuses it."""
    try:
        return _decode(data)
    except (struct.error, IndexError) as problem:
        raise PngError(f"a damaged PNG ({problem})")


def _decode(data: bytes) -> Image:
    if not data.startswith(SIGNATURE):
        raise PngError("not a PNG file")
    at, header, palette, trns, idat = 8, None, None, None, []
    while at + 8 <= len(data):
        length, kind = struct.unpack_from(">I4s", data, at)
        body = data[at + 8:at + 8 + length]
        if len(body) != length or at + 12 + length > len(data):
            raise PngError(f"the {kind!r} chunk ends early")
        if struct.unpack_from(">I", data, at + 8 + length)[0] != zlib.crc32(kind + body) & 0xFFFFFFFF:
            raise PngError(f"the {kind!r} chunk is damaged (CRC)")
        at += 12 + length
        if kind == b"IHDR":
            if length != 13:
                raise PngError("a damaged IHDR")
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = [tuple(body[i:i + 3]) for i in range(0, len(body) - 2, 3)]
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if not header:
        raise PngError("no IHDR")
    width, height, bits, color, _, _, interlace = header
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
    if channels is None or bits not in DEPTHS[color] or not width or not height or interlace > 1:
        raise PngError("an unsupported PNG layout")
    if color == 3 and not palette:
        raise PngError("a palette PNG without a palette")
    if width * height > 64_000_000:
        raise PngError("too large")
    try:
        # No more than the rows can hold (an interlaced image's passes add
        # a filter byte a row each): a bomb stops there.
        most = (height + 7) * (1 + (width * bits * channels + 7) // 8) * 2
        raw = zlib.decompressobj().decompress(b"".join(idat), most)
    except zlib.error as problem:
        raise PngError(f"damaged image data ({problem})")
    out = bytearray(width * height * 4)
    alpha_of = list(trns) + [255] * 256 if color == 3 and trns else None
    key = None
    if trns and color == 0 and len(trns) >= 2:
        key = struct.unpack(">H", trns[:2])[0]
    elif trns and color == 2 and len(trns) >= 6:
        key = struct.unpack(">HHH", trns[:6])

    def put(x, y, row, i, raw_line):
        o = (y * width + x) * 4
        if color == 3:
            index = row[i]
            r, g, b = palette[index] if index < len(palette) else (0, 0, 0)
            a = alpha_of[index] if alpha_of else 255
        elif color in (0, 4):
            v = row[i * channels]
            if bits < 8:
                v = v * 255 // ((1 << bits) - 1)
            r = g = b = v
            a = row[i * channels + 1] if color == 4 else 255
            if key is not None and _raw_value(raw_line, x, 0, bits, 1) == key:
                a = 0
        else:
            r, g, b = row[i * channels:i * channels + 3]
            a = row[i * channels + 3] if color == 6 else 255
            if key is not None and tuple(_raw_value(raw_line, x, c, bits, 3) for c in range(3)) == key:
                a = 0
        out[o:o + 4] = bytes((r, g, b, a))

    if interlace == 0:
        rows, _ = _unfilter(raw, width, height, bits, channels)
        for y, line in enumerate(rows):
            row = _samples(line, width, bits, channels)
            for x in range(width):
                put(x, y, row, x, line)
    else:
        start = 0
        for x0, y0, dx, dy in ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4),
                               (1, 0, 2, 2), (0, 1, 1, 2)):
            w = (width - x0 + dx - 1) // dx
            h = (height - y0 + dy - 1) // dy
            if w <= 0 or h <= 0:
                continue
            rows, start = _unfilter(raw, w, h, bits, channels, start)
            for j, line in enumerate(rows):
                row = _samples(line, w, bits, channels)
                for i in range(w):
                    put(x0 + i * dx, y0 + j * dy, row, i, line)
    return Image(width, height, bytes(out))


def _raw_value(line: bytes, x: int, channel: int, bits: int, channels: int) -> int:
    """A sample at its own depth, for the tRNS color key."""
    if bits == 16:
        at = (x * channels + channel) * 2
        return (line[at] << 8) | line[at + 1]
    if bits == 8:
        return line[x * channels + channel]
    per = 8 // bits
    return (line[x // per] >> (8 - bits - (x % per) * bits)) & ((1 << bits) - 1)


def read(path) -> Image:
    with open(path, "rb") as handle:
        return decode(handle.read())


# --- writing --------------------------------------------------------------------

def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def encode(image: Image) -> bytes:
    """RGBA, 8 bits, or RGB when every pixel is opaque."""
    opaque = image.opaque()
    channels = 3 if opaque else 4
    data = _rgb(image.rgba) if opaque else image.rgba
    stride = image.width * channels
    rows = [b"\x00" + data[y * stride:(y + 1) * stride] for y in range(image.height)]
    return (SIGNATURE + _chunk(b"IHDR", struct.pack(">IIBBBBB", image.width, image.height, 8,
                                                    2 if channels == 3 else 6, 0, 0, 0)) +
            _chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + _chunk(b"IEND", b""))


def write(path, image: Image):
    with open(path, "wb") as handle:
        handle.write(encode(image))


# --- operations --------------------------------------------------------------------

def crop(image: Image, left: int, top: int, width: int, height: int) -> Image:
    left, top = max(0, left), max(0, top)
    width, height = min(width, image.width - left), min(height, image.height - top)
    stride = image.width * 4
    rows = [image.rgba[(top + y) * stride + left * 4:(top + y) * stride + (left + width) * 4] for y in range(height)]
    return Image(width, height, b"".join(rows))


def middle(image: Image, width: int, height: int):
    """The rectangle (left, top, w, h) of the middle of the image at the
    shape width:height, as the port's resample takes it (art.c)."""
    cw, ch = float(image.width), float(image.height)
    if cw * height > ch * width:
        cw = ch * width / height
    else:
        ch = cw * height / width
    return (image.width - cw) / 2, (image.height - ch) / 2, cw, ch


def resample(image: Image, width: int, height: int, box=None) -> Image:
    """`width` x `height` from `box` (left, top, w, h, fractional; the whole
    image by default), each pixel the average of the source pixels under it,
    alpha-weighted: the port's resample (art.c) and the texture pack's
    (texture_pack.c load_pixels) average this way."""
    x0, y0, cw, ch = box if box else (0.0, 0.0, float(image.width), float(image.height))
    sw, sh, src = image.width, image.height, image.rgba
    lefts = []
    for x in range(width):
        left, right = int(x0 + cw * x / width), int(x0 + cw * (x + 1) / width)
        lefts.append((left, max(right, left + 1)))
    out = bytearray(width * height * 4)
    for y in range(height):
        top, bottom = int(y0 + ch * y / height), int(y0 + ch * (y + 1) / height)
        bottom = min(max(bottom, top + 1), sh)
        for x, (left, right) in enumerate(lefts):
            right = min(right, sw)
            r = g = b = a = n = 0
            for sy in range(top, bottom):
                row = sy * sw * 4
                for sx in range(left, right):
                    at = row + sx * 4
                    pa = src[at + 3]
                    r += src[at] * pa
                    g += src[at + 1] * pa
                    b += src[at + 2] * pa
                    a += pa
                    n += 1
            o = (y * width + x) * 4
            if a:
                out[o:o + 4] = bytes((r // a, g // a, b // a, a // max(n, 1)))
    return Image(width, height, bytes(out))


def flatten(image: Image, background=(0, 0, 0)) -> Image:
    """Opaque: each pixel over the background (the port's art reads a PNG
    over black, art.c load_png)."""
    if image.opaque():
        return image
    src, out = image.rgba, bytearray(image.rgba)
    alphas = src[3::4]
    for c in range(3):
        under = background[c]
        out[c::4] = bytes((v * a + under * (255 - a)) // 255 for v, a in zip(src[c::4], alphas))
    out[3::4] = b"\xff" * len(alphas)
    return Image(image.width, image.height, bytes(out))


def to_15bit(image: Image) -> Image:
    """Each color as VRAM keeps it, 5 bits a channel, expanded back as the
    picture does (extract_images.expand)."""
    out = bytearray(image.rgba.translate(_FIVE_BITS))
    out[3::4] = image.rgba[3::4]
    return Image(image.width, image.height, bytes(out))


_FIVE_BITS = bytes(((v >> 3) << 3) | (v >> 5) for v in range(256))


def scale_nearest(image: Image, factor: int) -> Image:
    if factor == 1:
        return image
    stride = image.width * 4
    rows = []
    for y in range(image.height):
        line = image.rgba[y * stride:(y + 1) * stride]
        wide = b"".join(line[x * 4:x * 4 + 4] * factor for x in range(image.width))
        rows.extend([wide] * factor)
    return Image(image.width * factor, image.height * factor, b"".join(rows))


def scale_to(image: Image, width: int, height: int) -> Image:
    """The image at any size, each pixel the nearest source one (no
    blending: pixel art stays sharp, a pixel a few wider than its
    neighbour at fractional sizes)."""
    if (width, height) == image.size:
        return image
    stride = image.width * 4
    columns = [min(image.width - 1, x * image.width // width) * 4 for x in range(width)]
    lines = {}
    rows = []
    for y in range(height):
        source = min(image.height - 1, y * image.height // height)
        line = lines.get(source)
        if line is None:
            row = image.rgba[source * stride:(source + 1) * stride]
            line = lines[source] = b"".join(row[x:x + 4] for x in columns)
        rows.append(line)
    return Image(width, height, b"".join(rows))


def ppm(image: Image, background=(0x55, 0x55, 0x55)) -> bytes:
    """The image as a binary PPM over a background (what Tk's PhotoImage
    takes without a PNG decoder)."""
    rgb = _rgb(flatten(image, background).rgba)
    return f"P6 {image.width} {image.height} 255 ".encode("ascii") + rgb
