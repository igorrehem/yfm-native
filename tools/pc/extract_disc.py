#!/usr/bin/env python3
"""Extract the player's disc image into plain files the port runs from.

The port reads the game the way the console's drive does, sector by sector
(src/pc/sdk/libds.c). This writes the disc's files as ordinary files under
game/disc/ (SLUS_014.11, SYSTEM.CNF, DATA/...), plus game/yfm-disc.txt, the
index that places each one at its sectors (src/pc/platform/disc_source.h).
The port then needs no .bin: every sector is rebuilt from the folder.

  * A data file whose sectors are all plain MODE2/Form1 data (the MRGs, the
    DATs, the executable) is written as its bytes, exactly as the ISO 9660
    file system holds it. The sector framing around them is regular and is
    rebuilt: sync, address, the subheader (0x08, 0x89 on the last sector) and
    the standard EDC/ECC.
  * A file with other sectors (MASTER.XA's interleaved voices, MOVIE.STR's
    video and audio) keeps its raw 2352-byte sectors, which hold the Form2
    audio and the subheaders the drive model filters on.
  * The few sectors outside any file (the system area, the volume descriptor,
    the directories and the lead-out gap) go raw into disc/system.raw.

Afterwards the folder is read back sector by sector and compared with the
image: every byte of every sector's header and data, and the EDC/ECC of a
sample of rebuilt sectors (the port regenerates them with the same standard
code). The image is not changed and can be deleted afterwards.

    python3 tools/pc/extract_disc.py [--disc PATH.bin] [--out game]
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import os
import random
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/project"))
from disc_image import DiscError, parse_directory_record, walk_iso  # noqa: E402

RAW = 2352
DATA = 2048
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
FORM1_SUBHEADER, FORM1_LAST = bytes([0, 0, 0x08, 0]), bytes([0, 0, 0x89, 0])
MANIFEST = "yfm-disc.txt"
FOLDER = "disc"
SAMPLE = 400   # rebuilt sectors whose EDC/ECC are checked (pure Python: about 3 ms each)


# The standard CD-ROM error detection and correction (ECMA-130), as the
# port computes it (disc_source.c).
ECC_F, ECC_B, EDC_TABLE = [0] * 256, [0] * 256, [0] * 256
for _i in range(256):
    _j = ((_i << 1) ^ (0x11D if _i & 0x80 else 0)) & 0xFF
    ECC_F[_i], ECC_B[_i ^ _j] = _j, _i
    _e = _i
    for _ in range(8):
        _e = (_e >> 1) ^ (0xD8018001 if _e & 1 else 0)
    EDC_TABLE[_i] = _e


def edc(data) -> int:
    value = 0
    for byte in data:
        value = (value >> 8) ^ EDC_TABLE[(value ^ byte) & 0xFF]
    return value


def ecc_block(sector, major_count, minor_count, major_mult, minor_inc, out_at):
    size = major_count * minor_count
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        a = b = 0
        for _ in range(minor_count):
            t = sector[12 + index]
            index += minor_inc
            if index >= size:
                index -= size
            a ^= t
            b ^= t
            a = ECC_F[a]
        a = ECC_B[ECC_F[a] ^ b]
        sector[out_at + major] = a
        sector[out_at + major + major_count] = a ^ b


def form1_tail(sector: bytearray) -> None:
    """Fill a MODE2/Form1 sector's EDC and ECC (the address takes no part in the ECC)."""
    sector[0x818:0x81C] = struct.pack("<I", edc(sector[0x10:0x818]))
    address = bytes(sector[12:16])
    sector[12:16] = b"\0\0\0\0"
    ecc_block(sector, 86, 24, 2, 86, 0x81C)
    ecc_block(sector, 52, 43, 86, 88, 0x8C8)
    sector[12:16] = address


def bcd(value: int) -> int:
    return (value // 10) << 4 | value % 10


def header(lba: int) -> bytes:
    position = lba + 150
    return SYNC + bytes([bcd(position // 4500), bcd(position // 75 % 60), bcd(position % 75), 2])


def rebuild_form1(lba: int, subheader: bytes, data: bytes, tail: bool) -> bytearray:
    sector = bytearray(RAW)
    sector[0:16] = header(lba)
    sector[16:20] = sector[20:24] = subheader
    sector[24:24 + DATA] = data
    if tail:
        form1_tail(sector)
    return sector


# ---------------------------------------------------------------------------

class Image:
    def __init__(self, path: Path):
        self.path = path
        size = path.stat().st_size
        if size % RAW:
            raise DiscError(f"{path}: {size} bytes is not a whole number of 2352-byte sectors (choose the .bin)")
        self.sectors = size // RAW
        self.handle = path.open("rb")

    def raw(self, lba: int) -> bytes:
        self.handle.seek(lba * RAW)
        sector = self.handle.read(RAW)
        if len(sector) != RAW:
            raise DiscError(f"{self.path}: short read at sector {lba}")
        return sector

    def read_extent(self, lba: int, size: int) -> bytes:
        return b"".join(self.raw(lba + i)[24:24 + DATA] for i in range((size + DATA - 1) // DATA))[:size]


def find_disc() -> Path | None:
    named = os.environ.get("MEMORIES_DISC")
    if named and named.lower().endswith(".bin"):
        return Path(named)
    for candidate in sorted(glob.glob(str(ROOT / "game" / "*.bin"))) + sorted(glob.glob(str(ROOT / "game" / "*.BIN"))):
        return Path(candidate)
    return None


def plan(image: Image):
    """[(kind, first, count, size, path)] covering every sector once, by sector."""
    pvd = image.read_extent(16, DATA)
    if pvd[1:6] != b"CD001":
        raise DiscError("sector 16 is not an ISO 9660 volume descriptor")
    files = walk_iso(image, parse_directory_record(pvd, 156))
    names = {path.upper() for path, _ in files}
    if "SLUS_014.11" not in names or "DATA/MODEL.MRG" not in names:
        raise DiscError("this is not the Yu-Gi-Oh! Forbidden Memories (USA, SLUS-01411) disc")
    entries, owned = [], set()
    for path, record in files:
        count = (record.size + DATA - 1) // DATA
        if not count:
            continue
        span = set(range(record.extent_lba, record.extent_lba + count))
        if span & owned or record.extent_lba + count > image.sectors:
            raise DiscError(f"{path}: its sectors overlap another file or leave the image")
        owned |= span
        regular = True
        for i in range(count):
            raw = image.raw(record.extent_lba + i)
            expected = FORM1_LAST if i == count - 1 else FORM1_SUBHEADER
            if raw[0:16] != header(record.extent_lba + i) or raw[16:20] != expected or raw[20:24] != expected:
                regular = False
                break
        if regular and record.size % DATA:
            tail = image.raw(record.extent_lba + count - 1)[24 + record.size % DATA:24 + DATA]
            regular = not any(tail)
        entries.append(("data" if regular else "raw", record.extent_lba, count, record.size, path))
    first = None
    for lba in range(image.sectors + 1):
        if lba < image.sectors and lba not in owned:
            first = lba if first is None else first
        elif first is not None:
            entries.append(("system", first, lba - first, 0, "system.raw"))
            first = None
    return sorted(entries, key=lambda entry: entry[1])


def extract(image: Image, out: Path):
    entries = plan(image)
    folder = out / FOLDER
    staging = out / (FOLDER + ".partial")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    lines = ["yfm-disc 1", f"sectors {image.sectors}"]
    system_offset = 0
    system = (staging / "system.raw").open("wb")
    for kind, first, count, size, path in entries:
        if kind == "system":
            for i in range(count):
                system.write(image.raw(first + i))
            lines.append(f"raw {first} {count} {system_offset} {FOLDER}/system.raw")
            system_offset += count
            continue
        target = staging / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as handle:
            for i in range(count):
                raw = image.raw(first + i)
                if kind == "data":
                    handle.write(raw[24:24 + DATA][:min(DATA, size - i * DATA)])
                else:
                    handle.write(raw)
        if kind == "data":
            lines.append(f"data {first} {count} {size} {FORM1_SUBHEADER.hex()} {FORM1_LAST.hex()} {FOLDER}/{path}")
        else:
            lines.append(f"raw {first} {count} 0 {FOLDER}/{path}")
    system.close()
    return lines, staging, folder


class Folder:
    """Reads sectors back from an extracted folder, as disc_source.c does."""

    def __init__(self, base: Path, lines: list[str]):
        """`base`: where the index's paths start (their first part, disc/, is the folder itself)."""
        def resolve(path):
            return base / path.split("/", 1)[1]
        self.entries = []
        for line in lines[2:]:
            fields = line.split()
            if fields[0] == "data":
                first, count, size = map(int, fields[1:4])
                self.entries.append(("data", first, count, size, bytes.fromhex(fields[4]), bytes.fromhex(fields[5]),
                                     resolve(fields[6]).open("rb")))
            else:
                first, count, offset = map(int, fields[1:4])
                self.entries.append(("raw", first, count, offset, None, None, resolve(fields[4]).open("rb")))

    def sector(self, lba: int, tail: bool) -> bytes:
        for kind, first, count, extra, sub, last, handle in self.entries:
            if first <= lba < first + count:
                index = lba - first
                if kind == "raw":
                    handle.seek((extra + index) * RAW)
                    return handle.read(RAW)
                handle.seek(index * DATA)
                data = handle.read(DATA).ljust(DATA, b"\0")
                return bytes(rebuild_form1(lba, last if index == count - 1 else sub, data, tail))
        raise DiscError(f"sector {lba} is in no entry")

    def data_sectors(self):
        return [first + i for kind, first, count, *_ in self.entries if kind == "data" for i in range(count)]


def verify(image: Image, base: Path, lines: list[str]) -> str:
    folder = Folder(base, lines)
    digest = hashlib.sha256()
    for lba in range(image.sectors):
        original = image.raw(lba)
        digest.update(original)
        rebuilt = folder.sector(lba, tail=False)
        kind = next(entry[0] for entry in folder.entries if entry[1] <= lba < entry[1] + entry[2])
        compared = 24 + DATA if kind == "data" else RAW
        if rebuilt[:compared] != original[:compared]:
            raise DiscError(f"sector {lba} does not read back from the folder as it is on the disc")
    sample = random.Random(1411).sample(folder.data_sectors(), SAMPLE)
    for lba in sample:
        if folder.sector(lba, tail=True) != image.raw(lba):
            raise DiscError(f"sector {lba}: the disc's EDC/ECC are not the standard ones the port rebuilds")
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--disc", type=Path, help="the raw .bin image (default: the first .bin in game/)")
    parser.add_argument("--out", type=Path, default=ROOT / "game", help="where yfm-disc.txt and disc/ go")
    arguments = parser.parse_args()
    disc = arguments.disc or find_disc()
    if not disc or not disc.is_file():
        print("extract_disc: no disc image; put the .bin of Yu-Gi-Oh! Forbidden Memories (USA) in game/",
              file=sys.stderr)
        return 1
    out = arguments.out.resolve()
    manifest = out / MANIFEST
    try:
        image = Image(disc)
        print(f"extract_disc: extracting {disc} into {out / FOLDER}")
        lines, staging, folder = extract(image, out)
        print("extract_disc: checking that the folder reads back as the disc")
        digest = verify(image, staging, lines)
    except (DiscError, OSError) as error:
        print(f"extract_disc: {error}", file=sys.stderr)
        return 1
    lines.insert(2, f"source-sha256 {digest}")
    if manifest.exists():
        manifest.unlink()
    shutil.rmtree(folder, ignore_errors=True)
    staging.rename(folder)
    temporary = manifest.with_name(MANIFEST + ".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(manifest)
    data = sum(1 for line in lines if line.startswith("data"))
    raw = sum(1 for line in lines if line.startswith("raw") and not line.endswith("/system.raw"))
    print(f"extract_disc: {data} files as plain data, {raw} with raw sectors (audio/video), "
          f"system area in disc/system.raw; the .bin is no longer needed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
