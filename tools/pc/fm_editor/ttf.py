"""TrueType outlines read and filled in Python, for the card-text preview
(card_text.py), so the editor still needs nothing but Python and Tkinter.

It reads what the port's HD text reads through FreeType: a character's
outline (the `glyf` table's quadratic contours, composite glyphs included)
and its advance, from a .ttf or the first font of a .ttc. OpenType fonts
with PostScript outlines (`CFF `, most .otf files) are refused with a
FontError that says so. `fill` turns flattened contours into 8-bit coverage
(non-zero winding, 4 sub-rows a pixel row and exact spans across), and
`embolden` makes them heavier as FT_Outline_EmboldenXY does.
"""
from __future__ import annotations

import math
import struct
from pathlib import Path


class FontError(Exception):
    pass


class Font:
    """One face of a TrueType file."""

    def __init__(self, path):
        self.path = Path(path)
        try:
            data = self.path.read_bytes()
        except OSError as problem:
            raise FontError(f"{self.path.name}: {problem.strerror or problem}") from None
        self.data = data
        start = 0
        if data[:4] == b"ttcf":
            if len(data) < 16:
                raise FontError(f"{self.path.name} is not a font file")
            start = struct.unpack_from(">I", data, 12)[0]
        if data[start:start + 4] == b"OTTO":
            raise FontError(f"{self.path.name} has PostScript (CFF) outlines, which the preview does not read; "
                            "a TrueType (.ttf) version of the font works")
        if len(data) < start + 12 or data[start:start + 4] not in (b"\x00\x01\x00\x00", b"true"):
            raise FontError(f"{self.path.name} is not a TrueType font")
        count = struct.unpack_from(">H", data, start + 4)[0]
        self.tables = {}
        for i in range(count):
            tag, _, offset, length = struct.unpack_from(">4sIII", data, start + 12 + 16 * i)
            self.tables[tag.decode("latin-1")] = (offset, length)
        for need in ("head", "maxp", "cmap", "loca", "glyf", "hhea", "hmtx"):
            if need not in self.tables:
                raise FontError(f"{self.path.name} has no '{need}' table")
        head = self.tables["head"][0]
        self.units = struct.unpack_from(">H", data, head + 18)[0] or 1000
        self.long_loca = struct.unpack_from(">h", data, head + 50)[0] == 1
        self.glyph_count = struct.unpack_from(">H", data, self.tables["maxp"][0] + 4)[0]
        self.metric_count = struct.unpack_from(">H", data, self.tables["hhea"][0] + 34)[0]
        self.cmap = self._read_cmap()
        self.name = self._read_name()
        self._outlines = {}

    # --- tables -----------------------------------------------------------

    def _read_cmap(self) -> dict:
        data, base = self.data, self.tables["cmap"][0]
        count = struct.unpack_from(">H", data, base + 2)[0]
        best = None
        for i in range(count):
            platform, encoding, offset = struct.unpack_from(">HHI", data, base + 4 + 8 * i)
            rank = {(3, 10): 0, (0, 4): 1, (3, 1): 2, (0, 3): 3, (0, 1): 4, (0, 0): 5}.get((platform, encoding))
            if rank is not None and (best is None or rank < best[0]):
                best = (rank, base + offset)
        if best is None:
            raise FontError(f"{self.path.name} has no Unicode character map")
        at = best[1]
        form = struct.unpack_from(">H", data, at)[0]
        out = {}
        if form == 4:
            segments = struct.unpack_from(">H", data, at + 6)[0] // 2
            ends = at + 14
            starts = ends + 2 * segments + 2
            deltas = starts + 2 * segments
            ranges = deltas + 2 * segments
            for s in range(segments):
                end = struct.unpack_from(">H", data, ends + 2 * s)[0]
                first = struct.unpack_from(">H", data, starts + 2 * s)[0]
                delta = struct.unpack_from(">h", data, deltas + 2 * s)[0]
                offset = struct.unpack_from(">H", data, ranges + 2 * s)[0]
                for c in range(first, min(end, 0xFFFE) + 1):
                    if offset:
                        where = ranges + 2 * s + offset + 2 * (c - first)
                        glyph = struct.unpack_from(">H", data, where)[0]
                        glyph = (glyph + delta) & 0xFFFF if glyph else 0
                    else:
                        glyph = (c + delta) & 0xFFFF
                    if glyph:
                        out[c] = glyph
        elif form == 12:
            groups = struct.unpack_from(">I", data, at + 12)[0]
            for g in range(groups):
                first, last, glyph = struct.unpack_from(">III", data, at + 16 + 12 * g)
                for c in range(first, min(last, 0x10FFFF) + 1):
                    out[c] = glyph + c - first
        else:
            raise FontError(f"{self.path.name}: character map format {form} is not read")
        return out

    def _read_name(self) -> str:
        if "name" not in self.tables:
            return self.path.stem
        data, base = self.data, self.tables["name"][0]
        count, strings = struct.unpack_from(">HH", data, base + 2)
        found = {}
        for i in range(count):
            platform, encoding, language, name_id, length, offset = struct.unpack_from(">6H", data, base + 6 + 12 * i)
            if name_id not in (1, 2, 4):
                continue
            raw = data[base + strings + offset:base + strings + offset + length]
            if platform in (0, 3):
                text = raw.decode("utf-16-be", "replace")
            elif platform == 1:
                text = raw.decode("mac-roman", "replace")
            else:
                continue
            if name_id not in found or (platform == 3 and language == 0x409):
                found[name_id] = text
        return found.get(4) or " ".join(v for v in (found.get(1), found.get(2)) if v) or self.path.stem

    def has(self, character: int) -> bool:
        return character in self.cmap

    def advance(self, character: int) -> float:
        """The character's advance in em units (1.0 = the em)."""
        glyph = self.cmap.get(character, 0)
        base = self.tables["hmtx"][0]
        index = min(glyph, self.metric_count - 1)
        return struct.unpack_from(">H", self.data, base + 4 * index)[0] / self.units

    # --- outlines ---------------------------------------------------------

    def _glyph_range(self, glyph):
        data, loca = self.data, self.tables["loca"][0]
        if glyph < 0 or glyph >= self.glyph_count:
            return 0, 0
        if self.long_loca:
            start, end = struct.unpack_from(">II", data, loca + 4 * glyph)
        else:
            start, end = (2 * v for v in struct.unpack_from(">HH", data, loca + 2 * glyph))
        return self.tables["glyf"][0] + start, end - start

    def _contours(self, glyph, depth=0):
        """The glyph's contours: lists of (x, y, on-curve) in font units."""
        at, length = self._glyph_range(glyph)
        if length <= 0 or depth > 8:
            return []
        data = self.data
        count = struct.unpack_from(">h", data, at)[0]
        p = at + 10
        if count >= 0:
            ends = struct.unpack_from(f">{count}H", data, p)
            p += 2 * count
            p += 2 + struct.unpack_from(">H", data, p)[0]
            points = ends[-1] + 1 if count else 0
            flags = []
            while len(flags) < points:
                flag = data[p]
                p += 1
                flags.append(flag)
                if flag & 8:
                    flags.extend([flag] * data[p])
                    p += 1
            flags = flags[:points]
            xs, ys = [], []
            for coords, short, same in ((xs, 2, 16), (ys, 4, 32)):
                value = 0
                for flag in flags:
                    if flag & short:
                        step = data[p]
                        p += 1
                        value += step if flag & same else -step
                    elif not flag & same:
                        value += struct.unpack_from(">h", data, p)[0]
                        p += 2
                    coords.append(value)
            contours, first = [], 0
            for end in ends:
                contours.append([(xs[i], ys[i], bool(flags[i] & 1)) for i in range(first, end + 1)])
                first = end + 1
            return contours
        contours = []
        while True:
            flags, component = struct.unpack_from(">HH", data, p)
            p += 4
            if flags & 1:
                a, b = struct.unpack_from(">hh", data, p)
                p += 4
            else:
                a, b = struct.unpack_from(">bb", data, p)
                p += 2
            xx, xy, yx, yy = 1.0, 0.0, 0.0, 1.0
            if flags & 8:
                xx = yy = struct.unpack_from(">h", data, p)[0] / 16384
                p += 2
            elif flags & 0x40:
                xx, yy = (v / 16384 for v in struct.unpack_from(">hh", data, p))
                p += 4
            elif flags & 0x80:
                xx, xy, yx, yy = (v / 16384 for v in struct.unpack_from(">hhhh", data, p))
                p += 8
            dx, dy = (a, b) if flags & 2 else (0, 0)    # point matching (rare) is left at the origin
            for contour in self._contours(component, depth + 1):
                contours.append([(x * xx + y * yx + dx, x * xy + y * yy + dy, on) for x, y, on in contour])
            if not flags & 0x20:
                break
        return contours

    def outline(self, character: int):
        """The character's contours in em units, y up, curves made into
        short lines: a list of lists of (x, y). None when the font lacks it."""
        if character not in self.cmap:
            return None
        if character in self._outlines:
            return self._outlines[character]
        scale = 1 / self.units
        out = []
        for contour in self._contours(self.cmap[character]):
            if len(contour) < 2:
                continue
            points = [(x * scale, y * scale, on) for x, y, on in contour]
            # Start on an on-curve point (or the middle of two off ones).
            start = next((i for i, p in enumerate(points) if p[2]), None)
            if start is None:
                a, b = points[0], points[1]
                points.insert(0, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, True))
                start = 0
            points = points[start:] + points[:start] + [points[start]]
            line = [(points[0][0], points[0][1])]
            control = None
            for x, y, on in points[1:]:
                if on:
                    if control is None:
                        line.append((x, y))
                    else:
                        _quad(line, control, (x, y))
                        control = None
                elif control is None:
                    control = (x, y)
                else:
                    middle = ((control[0] + x) / 2, (control[1] + y) / 2)
                    _quad(line, control, middle)
                    control = (x, y)
            if len(line) > 2:
                out.append(line[:-1] if line[0] == line[-1] else line)
        self._outlines[character] = out
        return out


def _quad(line, control, end, steps=8):
    x0, y0 = line[-1]
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        line.append((u * u * x0 + 2 * u * t * control[0] + t * t * end[0],
                     u * u * y0 + 2 * u * t * control[1] + t * t * end[1]))


def bbox(contours):
    xs = [x for c in contours for x, _ in c]
    ys = [y for c in contours for _, y in c]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def embolden(contours, across: float, down: float):
    """Heavier by `across` and `down` in all (half past each edge), each
    point moved out along its corner's bisector as FreeType's
    FT_Outline_EmboldenXY moves it; negative makes it lighter."""
    area = 0.0
    for c in contours:
        for i in range(len(c)):
            x0, y0 = c[i - 1]
            x1, y1 = c[i]
            area += x0 * y1 - x1 * y0
    sign = 1 if area > 0 else -1
    out = []
    for c in contours:
        n = len(c)
        normals = []
        for i in range(n):
            x0, y0 = c[i]
            x1, y1 = c[(i + 1) % n]
            dx, dy = x1 - x0, y1 - y0
            length = math.hypot(dx, dy) or 1.0
            normals.append((sign * dy / length, -sign * dx / length))
        moved = []
        for i in range(n):
            ax, ay = normals[i - 1]
            bx, by = normals[i]
            d = 1 + ax * bx + ay * by
            if d < 0.2:
                d = 0.2
            moved.append((c[i][0] + (ax + bx) / d * across / 2, c[i][1] + (ay + by) / d * down / 2))
        out.append(moved)
    return out


SUBROWS = 4


def fill(contours, width: int, height: int) -> bytearray:
    """Coverage (0-255) of `width` x `height` pixels, row by row, of
    contours in pixels with y down."""
    edges = []
    for c in contours:
        n = len(c)
        for i in range(n):
            x0, y0 = c[i]
            x1, y1 = c[(i + 1) % n]
            if y0 == y1:
                continue
            if y0 < y1:
                edges.append((y0, y1, x0, (x1 - x0) / (y1 - y0), 1))
            else:
                edges.append((y1, y0, x1, (x0 - x1) / (y0 - y1), -1))
    out = bytearray(width * height)
    if not edges:
        return out
    top = max(0, int(min(e[0] for e in edges)))
    bottom = min(height, int(math.ceil(max(e[1] for e in edges))))
    share = 1.0 / SUBROWS
    for row in range(top, bottom):
        acc = [0.0] * (width + 1)
        for k in range(SUBROWS):
            y = row + (k + 0.5) * share
            crossings = [(ex + (y - ey0) * slope, d) for ey0, ey1, ex, slope, d in edges if ey0 <= y < ey1]
            if not crossings:
                continue
            crossings.sort()
            winding = 0
            for i in range(len(crossings) - 1):
                winding += crossings[i][1]
                if not winding:
                    continue
                a, b = crossings[i][0], crossings[i + 1][0]
                if a < 0:
                    a = 0.0
                if b > width:
                    b = float(width)
                if b <= a:
                    continue
                ia, ib = int(a), int(b)
                if ia == ib:
                    acc[ia] += (b - a) * share
                else:
                    acc[ia] += (ia + 1 - a) * share
                    for x in range(ia + 1, ib):
                        acc[x] += share
                    acc[ib] += (b - ib) * share
        base = row * width
        for x in range(width):
            v = acc[x]
            if v > 0:
                out[base + x] = 255 if v >= 1 else int(v * 255 + 0.5)
    return out
