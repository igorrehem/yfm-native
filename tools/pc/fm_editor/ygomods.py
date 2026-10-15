"""Importing a .ygomods package into a port mod.

A .ygomods file is the package the old static recompilation's in-game
editor exported: a ZIP of INI and text files and PNGs. Its layout, as the
files describe themselves:

  manifest.ini              format = YGOFM-MOD-PACKAGE, version, game, counts
  cards/<id>/card.ini       key = value: name, description ("|" breaks a line),
                            attack, defense, level, type, attribute, star1,
                            star2, price, password, equips (the complete list of
                            monsters an equip card fits), ritual ("a, b, c -> r"),
                            and keys for colors and scripted effects
  cards/<id>/art.png, thumb.png, title.png
  drop_table_edits.ini      [duelist] then "<card> = <POW>, <BCD>, <TEC>": the
                            card's weight in each drop band, the rest of the
                            band sharing the remainder (the port's own rule);
                            "card =" / "when =" a scripted reward
  drop_missing_cards.ini    the same format, for the "drop missing cards" option
  cpu-duelists.ini          [duelist] then "name =", "ai = 9 bytes", and
                            "<card> = <weight>": the whole deck pool
  duelists/<n>/portrait.png the Free Duel portrait
  fusion-edits.txt          "a<TAB>b<TAB>result" (0 removes), "clear" empties
                            the table first
  dialogue.txt              the campaign's text, in the recomp's own numbering
  card_shop.ini, mod_settings.ini

What the port has a key for becomes that key; the rest (scripted effects,
colors, AI bytes, the shop, the recomp's own settings) is listed in the
report. No code of that project is used here, only its files' format.
"""
from __future__ import annotations

import json
import re
import struct
import zipfile
import zlib

from . import gamedata as g
from .model import Project, duelist_named, type_named
from .pools import apply_edit, normalize

BAND_NAMES = ("pow", "bcd", "tec")
PASSWORDS = 0xFB9800            # WA_MRG.MRG: per card u32 cost, u32 BCD password
FREE_DUEL_PORTRAITS = 0xF55000  # WA_MRG.MRG: 40 records of 0x980 bytes
KNOWN_CARD_KEYS = {"name", "description", "attack", "defense", "level", "type", "attribute", "star1", "star2",
                   "price", "password", "equips", "ritual"}
MAX_ENTRY = 8 << 20
PRICE_MOST = 999999             # the starchips a card can cost
WEIGHT_MOST = 65535             # a pool weight (a u16 on the disc)
# A folder of cards/ or duelists/ by number, zeros in front or not.
NUMBERED = re.compile(r"(cards|duelists)/0*(\d{1,9})/")


class PackageError(Exception):
    pass


def parse_ini(text: str) -> list:
    """[(section or None, key, value)] of an INI file; ";" and "#" start comments."""
    out, section = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in ";#":
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            out.append((section, key.strip(), value.strip()))
    return out


def _int(text, default=None):
    try:
        return int(str(text).strip(), 0)
    except ValueError:
        return default


def _choice(text, names):
    text = str(text).strip()
    for i, name in enumerate(names):
        if name and text.lower() == name.lower():
            return i
    return _int(text, -1)


def _canonical(name: str) -> str:
    """An entry's name with "/" and its card or duelist folder as a plain
    number: "cards\\007\\card.ini" is "cards/7/card.ini"."""
    name = name.replace("\\", "/")
    match = NUMBERED.match(name)
    if match:
        name = f"{match.group(1)}/{int(match.group(2))}/" + name[match.end():]
    return name


class Package:
    def __init__(self, path):
        try:
            self.zip = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as problem:
            raise PackageError(f"{path} is not a .ygomods package ({problem})")
        try:
            self.names = {_canonical(n): n for n in self.zip.namelist()}
            for info in self.zip.infolist():
                if info.file_size > MAX_ENTRY or ".." in info.filename.replace("\\", "/").split("/"):
                    raise PackageError(f"{info.filename}: an entry this importer will not read")
            manifest = dict((k, v) for _, k, v in parse_ini(self.text("manifest.ini") or ""))
            if manifest.get("format") != "YGOFM-MOD-PACKAGE":
                raise PackageError("manifest.ini does not say format = YGOFM-MOD-PACKAGE")
            self.manifest = manifest
        except BaseException:
            self.zip.close()
            raise

    def has(self, name):
        return name in self.names

    def data(self, name):
        if name not in self.names:
            return None
        try:
            return self.zip.read(self.names[name])
        except (zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError, EOFError, OSError) as problem:
            # a bad checksum, a password, a compression Python lacks, a cut-off file
            raise PackageError(f"{self.names[name]}: could not be read from the package ({problem})")

    def text(self, name):
        blob = self.data(name)
        return blob.decode("utf-8-sig", "replace") if blob is not None else None


def import_package(retail: g.GameData, retail_wa: bytes, path, mod_id="ygomods-import", name=None):
    """(project, report) for a .ygomods package over retail."""
    package = Package(path)
    try:
        return _import(package, retail, retail_wa, mod_id, name)
    finally:
        package.zip.close()


def _import(package, retail, retail_wa, mod_id, name):
    project = Project(retail)
    project.info.id = mod_id
    project.info.name = name or mod_id
    project.info.description = "Converted by the FM Editor from an old recomp's .ygomods package."
    report = ["a one-way conversion: the port does not read .ygomods, and what it has no key for is listed below"]
    unsupported = {}

    def unhandled(what, count=1):
        unsupported[what] = unsupported.get(what, 0) + count

    # --- cards ----------------------------------------------------------------
    card_ids = sorted({int(m.group(1)) for n in package.names for m in [re.match(r"cards/(\d{1,9})/", n)] if m})
    patches, equip_lists, ritual_lists, clamped = {}, {}, {}, 0

    def ranged(key, value, low, high):
        """value when it is low..high, else None and a report line."""
        if value is not None and low <= value <= high:
            return value
        unhandled(f"card \"{key}\" values out of range ({low} to {high})")
        return None

    for cid in card_ids:
        if not 1 <= cid <= g.CARD_COUNT:
            unhandled(f"cards past 722 (card {cid})")
            continue
        card = project.cards[cid]
        values = {k: v for _, k, v in parse_ini(package.text(f"cards/{cid}/card.ini") or "")}
        if "name" in values and values["name"]:
            card.name = values["name"]
        if "description" in values:
            card.description = values["description"].replace("|", "\n")
        for key, high in (("attack", 5110), ("defense", 5110), ("level", 12)):
            if key in values:
                value = ranged(key, _int(values[key]), 0, high)
                if value is not None:
                    setattr(card, key, value)
        if "type" in values:
            t = type_named(values["type"]) if not values["type"].isdigit() else int(values["type"])
            if ranged("type", t, 0, g.TYPE_EQUIP) is not None:
                card.type = t
        if "attribute" in values:
            a = ranged("attribute", _choice(values["attribute"], g.ATTRIBUTE_NAMES), 0, len(g.ATTRIBUTE_NAMES) - 1)
            if a is not None:
                card.attribute = a
        for key in ("star1", "star2"):
            if key in values:
                star = ranged(key, _choice(values[key], g.STAR_NAMES), 0, len(g.STAR_NAMES) - 1)
                if star is not None:
                    setattr(card, key, star)
        if "equips" in values:
            equip_lists[cid] = {_int(x) for x in values["equips"].replace(";", ",").split(",") if _int(x)}
        if "ritual" in values:
            match = re.match(r"\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*->\s*(\d+)", values["ritual"])
            if match:
                ritual_lists[cid] = tuple(int(x) for x in match.groups())
            else:
                unhandled("ritual recipes it could not read")
        # Passwords and costs: a data patch of WA_MRG.MRG's table, when they change.
        if ("price" in values or "password" in values) and len(retail_wa or b"") >= PASSWORDS + 8 * (cid + 1):
            at = PASSWORDS + 8 * cid
            cost, code = struct.unpack_from("<II", retail_wa, at)
            new_cost = _int(values.get("price"), cost)
            if not 0 <= new_cost <= PRICE_MOST:
                new_cost = min(max(new_cost, 0), PRICE_MOST)
                clamped += 1
            password = values.get("password", "")
            new_code = int(password, 16) if re.fullmatch(r"\d{1,8}", password or "") else code
            if (new_cost, new_code) != (cost, code):
                patches[at] = struct.pack("<II", new_cost, new_code)
        for part, key in (("art.png", "art"), ("thumb.png", "thumbnail"), ("title.png", "title")):
            blob = package.data(f"cards/{cid}/{part}")
            if blob:
                path_in_mod = f"images/{cid:03d}-{part}"
                project.files[path_in_mod] = blob
                project.card_extra.setdefault(cid, {})[key] = path_in_mod
        for key in values:
            if key not in KNOWN_CARD_KEYS:
                unhandled(f"card key \"{key}\"")
    # Equips and rituals once every card has its type: the port takes an
    # equips entry for an equip card only, a rituals one for a ritual card,
    # naming cards of the disc (src/pc/cards/tables.c).
    for cid, monsters in equip_lists.items():
        if project.cards[cid].type != g.TYPE_EQUIP:
            unhandled("\"equips\" on cards that are not equip cards")
            continue
        fits = {m for m in monsters if m in project.cards and project.cards[m].is_monster()}
        if fits != monsters:
            unhandled("\"equips\" naming no monster of the disc", len(monsters - fits))
        project.equips[cid] = fits
    for cid, recipe in ritual_lists.items():
        if project.cards[cid].type != g.TYPE_RITUAL:
            unhandled("\"ritual\" on cards that are not ritual cards")
        elif not all(1 <= c <= g.CARD_COUNT for c in recipe):
            unhandled("ritual recipes naming no card of the disc")
        else:
            project.rituals[cid] = recipe
    if clamped:
        report.append(f"cards: {clamped} prices outside 0 to {PRICE_MOST} starchips, brought inside")
    changed = sum(1 for cid in card_ids if cid in project.retail.cards and project.card_changed(cid))
    report.append(f"cards: {len(card_ids)} in the package, {changed} differ from retail")
    if patches:
        project.other.setdefault("data", []).append({"file": "\\DATA\\WA_MRG.MRG;1", "patch": [
            {"at": f"0x{at:X}", "bytes": blob.hex(" ").upper()} for at, blob in sorted(patches.items())]})
        report.append(f"cards: {len(patches)} passwords or starchip costs (\"price\") changed, as a data patch of "
                      "WA_MRG.MRG")

    # --- fusions ----------------------------------------------------------------
    text = package.text("fusion-edits.txt")
    if text is not None:
        count = 0
        for line in text.splitlines():
            line = line.split("#")[0].strip()
            if not line:
                continue
            if line.lower() == "clear":
                project.fusions = {}
                report.append("fusions: the package clears the disc's table first")
                continue
            parts = [_int(p) for p in re.split(r"[\t ,]+", line)]
            if len(parts) != 3 or None in parts:
                unhandled("fusion lines it could not read")
                continue
            a, b, result = parts
            if a in project.cards and b in project.cards and (result == 0 or result in project.cards):
                project.set_fusion(a, b, result or None)
                count += 1
        report.append(f"fusions: {count} edits read")

    # --- pools ------------------------------------------------------------------
    def drop_file(name, label):
        text = package.text(name)
        if text is None:
            return
        listed = {}
        for section, key, value in parse_ini(text):
            d = duelist_named(section or "")
            if section and section.lower().startswith("starchip reward"):
                unhandled("StarChip reward rules")
                continue
            if d < 0:
                unhandled(f"{label} sections naming no opponent")
                continue
            if key in ("card", "when"):
                unhandled("scripted rewards (card = / when =)")
                continue
            table = re.fullmatch(r"(pow|bcd|tec)_table", key)
            if table:
                pool = {}
                for item in value.split(","):
                    if ":" in item:
                        cid, weight = (_int(x) for x in item.split(":", 1))
                        if cid in project.cards and weight is not None and 0 < weight <= WEIGHT_MOST:
                            pool[cid] = weight
                        elif weight:
                            unhandled(f"{label} table weights out of range (1 to {WEIGHT_MOST}) or for no card")
                if pool:
                    project.pools[d][table.group(1)] = normalize(pool)
                continue
            cid = _int(key)
            weights = [_int(x) for x in value.split(",")]
            if cid not in project.cards or len(weights) != 3 or None in weights:
                unhandled(f"{label} lines it could not read")
                continue
            if not all(0 <= w <= WEIGHT_MOST for w in weights):
                unhandled(f"{label} lines with weights out of range (0 to {WEIGHT_MOST})")
                continue
            for band, weight in zip(BAND_NAMES, weights):
                listed.setdefault((d, band), {})[cid] = weight
        refused = 0
        for (d, band), cards in listed.items():
            result = apply_edit(project.pools[d][band], cards)
            if result is None:
                refused += 1
            else:
                project.pools[d][band] = result
        report.append(f"drops: {label}: {len(listed)} pools edited" + (f", {refused} refused (no card left)" if refused else ""))

    settings = {k: v for _, k, v in parse_ini(package.text("mod_settings.ini") or "")}
    if package.has("drop_missing_cards.ini"):
        if settings.get("drop_missing_cards", "1") != "0":
            drop_file("drop_missing_cards.ini", "drop_missing_cards.ini")
        else:
            report.append("drops: drop_missing_cards.ini left out (its option is off in mod_settings.ini)")
    drop_file("drop_table_edits.ini", "drop_table_edits.ini")

    text = package.text("cpu-duelists.ini")
    if text is not None:
        decks, renamed = {}, {}
        for section, key, value in parse_ini(text):
            d = duelist_named(section or "")
            if d < 0:
                unhandled("cpu-duelists.ini sections naming no opponent")
                continue
            if key == "ai":
                unhandled("AI profile bytes (ai =)")
                continue
            if key == "name":
                renamed[d] = value
                continue
            cid, weight = _int(key), _int(value)
            if cid in project.cards and weight is not None and 0 <= weight <= WEIGHT_MOST:
                decks.setdefault(d, {})[cid] = weight
            else:
                unhandled(f"cpu-duelists.ini lines with no card or a weight out of range (0 to {WEIGHT_MOST})")
        for d, pool in decks.items():
            result = apply_edit(project.pools[d]["deck"], {c: w for c, w in pool.items() if w}, replace=True, deck=True)
            if result is None:
                report.append(f"decks: {g.DUELIST_NAMES[d]}'s deck left as it was (fewer than 14 cards)")
            else:
                project.pools[d]["deck"] = result
        report.append(f"decks: {len(decks)} opponents' deck pools read")
        renamed = {d: n for d, n in renamed.items() if n != g.DUELIST_NAMES[d]}
        if renamed:
            listing = ["# Duelist names from a .ygomods package (notes/translation.md).", "", "@bank names", ""]
            for d, new in sorted(renamed.items()):
                listing += [f"[{0x8000 + 0x328 + d:04X}]", new.replace("{", "(").replace("}", ")") + "{end}", ""]
            project.files["text.txt"] = ("\n".join(listing) + "\n").encode("utf-8")
            project.other["text"] = "text.txt"
            report.append(f"text: {len(renamed)} opponents renamed, as a text listing (text.txt)")

    # --- portraits ---------------------------------------------------------------
    portraits = sorted(int(m.group(1)) for n in package.names
                       for m in [re.fullmatch(r"duelists/(\d{1,9})/portrait\.png", n)] if m)
    if portraits:
        entries = []
        for d in portraits:
            if not 0 <= d < 40:
                continue
            record = FREE_DUEL_PORTRAITS + d * 0x980
            project.files[f"textures/portraits/freeduel-{d:02d}.png"] = package.data(f"duelists/{d}/portrait.png")
            entries.append({"file": f"portraits/freeduel-{d:02d}.png", "archive": "WA_MRG.MRG", "offset": record,
                            "words": 24, "rows": 48, "bpp": 8, "clut_offset": record + 0x900, "clut_entries": 64})
        project.files["textures/manifest.json"] = (json.dumps(entries, indent=2) + "\n").encode("utf-8")
        project.other["textures"] = "textures"
        report.append(f"portraits: {len(entries)} Free Duel portraits, as a texture pack (textures/)")

    # --- the rest -------------------------------------------------------------------
    if package.has("dialogue.txt"):
        unhandled("dialogue.txt (the recomp's own numbering of the game's codes; translate with "
                  "tools/pc/text_listing.py instead)")
    if package.has("card_shop.ini"):
        unhandled("card_shop.ini (the recomp's card shop)")
    if settings:
        unhandled("mod_settings.ini (the recomp's MODS and CHEATS rows)", len(settings))
    for what, count in sorted(unsupported.items()):
        report.append(f"not imported: {what}" + (f" ({count})" if count > 1 else ""))
    project.files["import-report.txt"] = ("\n".join(report) + "\n").encode("utf-8")
    return project, report
