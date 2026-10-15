"""The duelists a mod adds past the disc's thirty-nine, and the disc's own it
takes over (notes/more-duelists.md; src/pc/free_duel/duelists.c).

A mod writes them as one file to a duelist:

    duelists/<id>.json      who it is: {"copy": "Simon Muran", "name": ...}
    decks/<id>.json         its deck pool, as a "decks" entry
    drops/<id>.json         its drop pools, as a "drops" entry
    portraits/<id>.png      its face

or as a "duelists" list in mod.json (each entry with its "id"), or as a file
that list is in. The editor reads all three and writes each duelist back
where it found it; a duelist made here goes in the folders.

A copy ("copy") is a duelist of its own: the editor keeps its four pools as
the game deals them (RosterDuelist.pools), starting from its base's, and
writes them as decks/<id>.json and drops/<id>.json against the base's disc
pools, which is what the game edits for it (tables.c Tables_PoolFor is handed
the base's disc pool). A replacement ("replace") takes over a disc duelist's
name, face and way of playing: its pools stay Project.pools[d], written in
mod.json's "decks" and "drops" by the disc's name as before, which still
reaches it.

A copy's fixed deck (decks/<id>.json with "fixed": true) is a
fixed_decks.FixedDeck in Project.fixed naming its entry, edited as a disc
duelist's is and written back to that file.

"unlock", "ai" and "ranks" stay in RosterDuelist.extra as written;
duelist_rules.py reads and edits them there. Anything else an entry carries
is kept as written too.

Where an added duelist lands on the Free Duel grid is worked out as
place_pending does for this mod alone: the entries that ask for a "slot"
first, in the order they are read (the manifest's list, then the folder's
files sorted by name), then everyone else at the lowest free place. Another
mod, or the player's own folder, can take a place first; the game settles
that, and its Mods window says so.
"""
from __future__ import annotations

import copy as _copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import pngio, portrait
from .gamedata import DUELIST_COUNT, DUELIST_NAMES, POOLS
from .model import KEY_RE, duelist_named, letters

FIRST_SLOT = DUELIST_COUNT          # DUELISTS_RETAIL_COUNT: the first id a mod's duelist has
LAST_SLOT = 127                     # DUELIST_TABLE_COUNT - 1: an id of 128 reads back negative
PAGE = 40                           # FREE_DUEL_GRID_ENTRY_COUNT: duelists a page
COLUMNS = 5                         # FREE_DUEL_GRID_COLUMN_COUNT: the grid fills a row of five, then the next
KEY_MAX = 63                        # duelists.c KEY_MAX - 1
NAME_MAX = 31                       # DUELIST_NAME_MAX - 1: what Duelists_Name keeps to match on
FOLDERS = ("duelists", "decks", "drops", "portraits")
# An id the editor reads: any a file can be named (the spec's own example
# has a space). One it makes is KEY_RE's, letters, digits, - and _.
FILE_KEY_RE = re.compile(r'^[^/\\:*?"<>|\x00-\x1f]+$')


@dataclass(eq=False)
class RosterDuelist:
    """One "duelists" entry. `key` is its id (a folder file's name);
    `base` the disc duelist it copies or, with `replace`, takes over.
    eq=False: an entry is itself, two alike are still two."""
    key: str
    base: int
    replace: bool = False
    name: str = ""                  # its own name; "" for its base's (a replacement's: the disc's)
    slot: object = None             # the id it asks for, 40-127, or None for the first free place
    portrait: bytes = field(default=None, repr=False)   # its PNG's bytes, or None: its base's face
    portrait_path: str = None       # "portrait" as written, when the PNG is not portraits/<key>.png
    pools: dict = field(default=None, repr=False)       # a copy's {pool: {card: weight}}, as the game deals them
    kept: dict = field(default_factory=dict)    # pool -> {name as written: weight} naming no card here
    extra: dict = field(default_factory=dict)   # the entry's other keys (ai, unlock, ranks...) as written
    origin: str = "folder"          # "folder", "manifest" (mod.json's list) or "file" (the file it names)
    written: dict = field(default=None, repr=False)     # the entry as it was read; None when made here

    @property
    def copy(self) -> bool:
        return not self.replace


# --- the project's roster ------------------------------------------------------

def entries(project) -> list:
    return getattr(project, "roster", [])


def copies(project) -> list:
    return [e for e in entries(project) if not e.replace]


def replacement(project, d: int):
    """The entry taking over disc duelist d: the last, as the game has it."""
    found = None
    for e in entries(project):
        if e.replace and e.base == d:
            found = e
    return found


def find(project, key: str):
    for e in entries(project):
        if e.key == key:
            return e
    return None


def identity(project, e) -> str:
    return f"{project.info.id}:{e.key}"


# --- an opponent, whoever it is (the pool tables' "subjects") ---------------------------------

def subjects(project) -> list:
    """Every duelist with pools of its own: the disc's (ids) and the copies."""
    return list(range(len(project.pools))) + copies(project)


def pools_of(project, s) -> dict:
    return project.pools[s] if isinstance(s, int) else s.pools


def retail_pool(project, s, pool: str) -> dict:
    """What the game edits for it: a copy has its base's disc pool."""
    return project.retail.pools[s if isinstance(s, int) else s.base][pool]


def kept_of(project, s, pool: str) -> dict:
    if isinstance(s, int):
        return project.kept_pools.get((s, pool), {})
    return s.kept.get(pool, {})


def keep(project, s, pool: str, names: dict):
    if isinstance(s, int):
        project.kept_pools.setdefault((s, pool), {}).update(names)
    else:
        s.kept.setdefault(pool, {}).update(names)


def label(project, s) -> str:
    """How a duelist is named in a message: its name as the mod has it."""
    if isinstance(s, int):
        return shown_name(project, s)
    return s.name or DUELIST_NAMES[s.base]


def shown_name(project, s) -> str:
    """The name the grid and the duel show (Duelists_Name)."""
    if isinstance(s, int):
        e = replacement(project, s)
        return e.name if e is not None and e.name else DUELIST_NAMES[s] if s < len(DUELIST_NAMES) else str(s)
    return s.name or DUELIST_NAMES[s.base]


def opponents(project) -> list:
    """[(label, duelist)] of every opponent, for a list to pick from: the
    disc's 1 to 39 by number, then the mod's own by the id they get on the
    grid ("40 Dark Simon"); one with no place is in no duel."""
    out = [(f"{d} {shown_name(project, d)}", d) for d in range(1, len(project.pools))]
    placed = sorted((slot, e) for e, slot in placement(project).items() if slot is not None)
    return out + [(f"{slot} {shown_name(project, e)}", e) for slot, e in placed]


def named(project, text):
    """A duelist a manifest names, as Duelists_Named finds one: a disc id, an
    identity ("<mod>:<id>"), a name; the disc's duelist (an id), or a copy
    (its entry), or None. A replacement answers for the disc duelist it
    takes over, by its identity or its new name."""
    text = str(text)
    if not text:
        return None
    if text.isdigit():
        d = int(text)
        if d < DUELIST_COUNT:
            return d
        for e, slot in placement(project).items():
            if slot == d:
                return e
        return None
    for e in entries(project):
        if text == identity(project, e):
            return e.base if e.replace else e
    d = duelist_named(text)
    if d >= 0:
        return d
    for e in entries(project):
        if e.replace and e.name and letters(e.name) == letters(text):
            return e.base
    for e, slot in sorted(placement(project).items(), key=lambda item: item[1]):
        if letters(shown_name(project, e)) == letters(text):
            return e
    return None


# --- places on the grid ---------------------------------------------------------------

def read_order(project) -> list:
    """The order the game reads the entries in: the manifest's list (or the
    file it names), then the folder's files by name (duelists.c)."""
    listed = [e for e in entries(project) if e.origin != "folder"]
    folder = sorted((e for e in entries(project) if e.origin == "folder"), key=lambda e: e.key.encode("utf-8"))
    return listed + folder


def placement(project) -> dict:
    """{copy: the id it gets} as place_pending hands them out for this mod: a
    second entry of one identity is left out (None), as the game leaves it."""
    out, taken, seen, waiting = {}, set(), set(), []
    for e in read_order(project):
        if e.replace:
            continue
        if e.key in seen:
            out[e] = None
            continue
        seen.add(e.key)
        if isinstance(e.slot, int) and FIRST_SLOT <= e.slot <= LAST_SLOT and e.slot not in taken:
            out[e] = e.slot
            taken.add(e.slot)
        else:
            waiting.append(e)
    following = FIRST_SLOT
    for e in waiting:
        slot = following
        while slot <= LAST_SLOT and slot in taken:
            slot += 1
        if slot > LAST_SLOT:
            out[e] = None       # "no room left": the grid holds 128
            continue
        out[e] = slot
        taken.add(slot)
        following = slot + 1
    return out


def slot_of(project, s):
    """A duelist's id: the disc's own, or where a copy lands (None: nowhere)."""
    return s if isinstance(s, int) else placement(project).get(s)


def page_of(slot: int) -> int:
    """The Free Duel page (1 the disc's) an id is shown on."""
    return slot // PAGE + 1


def cell_of(slot: int) -> tuple:
    """(row, column) of an id's cell on its page, from 0: five to a row."""
    cell = slot % PAGE
    return cell // COLUMNS, cell % COLUMNS


def pages(project) -> int:
    """How many pages the grid has with this mod alone: one past the disc's
    for every forty ids up to the highest placed (Duelists_Count)."""
    slots = [s for s in placement(project).values() if s is not None]
    return page_of(max(slots)) if slots else 1


def where(slot) -> str:
    """"Page 2, row 2, column 1" for an id."""
    if slot is None:
        return "no place on the grid"
    row, column = cell_of(slot)
    return f"page {page_of(slot)}, row {row + 1}, column {column + 1}"


# --- editing ---------------------------------------------------------------------------

def slug(text: str) -> str:
    """An id from a name: letters, digits and hyphens, lower case."""
    out = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return out[:KEY_MAX] or "duelist"


def free_key(project, wanted: str, but=None) -> str:
    """`wanted`, or wanted-2, -3... when another entry has it."""
    keys = {e.key.lower() for e in entries(project) if e is not but}
    key, n = wanted, 2
    while key.lower() in keys:
        key = f"{wanted[:KEY_MAX - 4]}-{n}"
        n += 1
    return key


def add_copy(project, base: int, name: str = "", slot=None, key: str = None) -> RosterDuelist:
    """A new duelist copying disc duelist `base`, in the folders, its pools
    its base's as the mod has them now."""
    if not 1 <= base < DUELIST_COUNT:
        raise ValueError("a duelist copies one of the disc's 39 (1 to 39)")
    key = free_key(project, key or slug(name or DUELIST_NAMES[base]))
    e = RosterDuelist(key=key, base=base, name=name if name != DUELIST_NAMES[base] else "", slot=slot,
                      pools={pool: dict(project.pools[base][pool]) for pool in POOLS})
    project.roster.append(e)
    return e


def duplicate(project, e: RosterDuelist) -> RosterDuelist:
    """Another copy with everything this one has, at the next free place."""
    other = _copy.deepcopy(e)
    other.replace = False
    other.origin = "folder"
    other.written = None
    other.slot = None
    other.portrait_path = None
    other.name = (e.name or DUELIST_NAMES[e.base]) + " 2"
    other.key = free_key(project, slug(other.name))
    if other.pools is None:
        other.pools = {pool: dict(project.pools[e.base][pool]) for pool in POOLS}
    project.roster.append(other)
    from . import fixed_decks
    deck = fixed_decks.deck_of(project, e) if e.copy else None
    if deck is not None:        # its fixed deck too, in a file of its own
        fixed_decks.set_deck(project, other, deck.cards).kept = dict(deck.kept)
    return other


def remove(project, e: RosterDuelist):
    """Out of the mod, with its fixed deck."""
    from . import fixed_decks
    project.roster.remove(e)
    fixed_decks.remove(project, e)


def take_over(project, d: int) -> RosterDuelist:
    """Disc duelist d's replacement, made when there is none (its id from the
    disc's name: portraits/<id>.png is then its face)."""
    e = replacement(project, d)
    if e is None:
        e = RosterDuelist(key=free_key(project, slug(DUELIST_NAMES[d])), base=d, replace=True)
        project.roster.append(e)
    return e


def prune(project, e: RosterDuelist):
    """A replacement that no longer changes anything is no entry at all."""
    if e.replace and not e.name and e.portrait is None and not e.portrait_path and not e.extra:
        if e in project.roster:
            project.roster.remove(e)


def set_name(project, s, name: str):
    """A duelist's name; a disc duelist's makes (or drops) its replacement."""
    name = name.strip()
    if isinstance(s, int):
        e = take_over(project, s)
        e.name = "" if name == DUELIST_NAMES[s] else name
        prune(project, e)
    else:
        s.name = "" if name == DUELIST_NAMES[s.base] else name


def set_portrait(project, s, png: bytes):
    """The PNG a duelist wears; a disc duelist's goes on its replacement."""
    pngio.decode(png)       # a PngError now rather than in the game
    e = take_over(project, s) if isinstance(s, int) else s
    e.portrait = bytes(png)


def revert_portrait(project, s):
    """Its base's face again (a disc duelist's own)."""
    e = replacement(project, s) if isinstance(s, int) else s
    if e is None:
        return
    e.portrait = None
    e.portrait_path = None
    prune(project, e)


def has_portrait(project, s) -> bool:
    e = replacement(project, s) if isinstance(s, int) else s
    return e is not None and (e.portrait is not None or bool(e.portrait_path))


def rename_key(project, e: RosterDuelist, key: str):
    if not KEY_RE.match(key) or len(key) > KEY_MAX:
        raise ValueError(f"an id is 1 to {KEY_MAX} letters, digits, hyphens or underscores")
    if any(o is not e and o.key.lower() == key.lower() for o in entries(project)):
        raise ValueError(f"another duelist has the id {key}")
    e.key = key


# --- pictures ---------------------------------------------------------------------------

_decoded = {}


def picture(png: bytes):
    """The PNG as an Image (kept: a list draws the same few many times), or
    None when it cannot be read."""
    if png is None:
        return None
    digest = hashlib.sha1(png).digest()
    if digest not in _decoded:
        try:
            _decoded[digest] = pngio.decode(png)
        except pngio.PngError:
            _decoded[digest] = None
        if len(_decoded) > 256:
            _decoded.pop(next(iter(_decoded)))
    return _decoded[digest]


def own_picture(project, s):
    """The PNG a duelist wears in place of its base's face, or None."""
    e = replacement(project, s) if isinstance(s, int) else s
    return picture(e.portrait) if e is not None else None


def face(project, wa, s, scale: int = 1):
    """The portrait as the grid draws it at Internal `scale`x: its own PNG
    made as the game makes it, else its base's disc portrait (None without
    the archive)."""
    image = own_picture(project, s)
    if image is not None:
        return portrait.in_game(image, scale)
    if wa is None:
        return None
    base = s if isinstance(s, int) else s.base
    return pngio.scale_nearest(portrait.disc_portrait(wa, base), scale)


# --- reading -------------------------------------------------------------------------------

def _read_entry(project, value, key, origin: str, where: str, messages: list):
    """An entry as read_one_duelist reads it, or None when the game would
    leave it out (it is then kept as written)."""
    if not isinstance(value, dict):
        messages.append(f"{where}: an object, with a copy and a name; kept as written")
        return None
    over = value.get("replace")
    if over is not None:
        base = duelist_named(over) if isinstance(over, (str, int)) and not isinstance(over, bool) else -1
        if not 1 <= base < DUELIST_COUNT:
            messages.append(f"{where}: replace names no disc duelist (1-39); kept as written")
            return None
    else:
        copy = value.get("copy")
        base = duelist_named(copy) if isinstance(copy, (str, int)) and not isinstance(copy, bool) else -1
        if not 1 <= base < DUELIST_COUNT:
            messages.append(f"{where}: copy names no disc duelist (1-39); kept as written")
            return None
    if not key or not isinstance(key, str) or len(key) > KEY_MAX:
        messages.append(f"{where}: no id of {KEY_MAX} letters or fewer; kept as written")
        return None
    e = RosterDuelist(key=key, base=base, replace=over is not None, origin=origin, written=_copy.deepcopy(value))
    name = value.get("name")
    if isinstance(name, str):
        e.name = name
    slot = value.get("slot")
    if isinstance(slot, int) and not isinstance(slot, bool) and FIRST_SLOT <= slot <= LAST_SLOT and not e.replace:
        e.slot = slot
    path = value.get("portrait")
    if isinstance(path, str):
        e.portrait_path = path
    # A folder's file takes its id from its name, and an "id" in it is
    # passed over: kept as written, like anything else the editor has no
    # field for.
    taken = {"copy", "replace", "portrait"} | ({"id"} if origin != "folder" else set())
    if isinstance(name, str):
        taken.add("name")
    if e.slot is not None:
        taken.add("slot")
    if over is not None:
        taken.discard("copy")     # copy beside replace is left out by the game; kept as written
    e.extra = {k: _copy.deepcopy(v) for k, v in value.items() if k not in taken}
    if e.copy:
        e.pools = {pool: dict(project.retail.pools[base][pool]) for pool in POOLS}
    return e


def _read_portrait(project, e: RosterDuelist, folder, messages: list):
    if folder is None:
        return
    folder = Path(folder)
    if e.portrait_path is not None:
        from .art import contained
        if not contained(e.portrait_path):
            messages.append(f"duelist {e.key}: portrait {e.portrait_path} is not a path inside the mod")
            return
        rel = e.portrait_path
    else:
        rel = f"portraits/{e.key}.png"
    path = folder / rel
    if not path.is_file():
        if e.portrait_path is not None:
            messages.append(f"duelist {e.key}: no file {rel}")
        return
    data = path.read_bytes()
    try:
        pngio.decode(data)
    except pngio.PngError as problem:
        messages.append(f"duelist {e.key}: {rel} is not a PNG it can read ({problem}); kept as written")
        return
    e.portrait = data
    project.roster_owned.add(rel)


def read(project, value, folder, messages: list):
    """mod.json's "duelists" (a list, or a file holding one) and the folder's
    duelists/ files, into project.roster; before the pools are read, which
    may name them."""
    project.roster = []
    project.roster_kept = []
    project.roster_raw = None
    project.roster_file = None
    project.roster_owned = set()
    if value is not None:
        listed, origin = value, "manifest"
        if isinstance(value, str):
            from .art import contained
            from .manifest import read_json
            project.roster_file = value
            listed = None
            if folder is not None and contained(value) and (Path(folder) / value).is_file():
                try:
                    listed = read_json(Path(folder) / value)
                    origin = "file"
                except (OSError, ValueError) as problem:
                    messages.append(f"duelists: {value}: {problem}; kept as written")
            elif folder is not None:
                messages.append(f"duelists: {value} is no file inside the mod; kept as written")
            if listed is None:
                project.roster_file_unread = True
                listed = []
            else:
                project.roster_file_unread = False
                project.roster_owned.add(value)
        if not isinstance(listed, list):
            messages.append("\"duelists\" is a list of duelists to add; kept as written")
            if origin == "manifest":
                project.roster_raw = listed
            else:
                project.roster_file_unread = True      # its file stays as it is
            listed = []
        for index, item in enumerate(listed):
            where = f"duelists[{index}]"
            key = item.get("id") if isinstance(item, dict) else None
            if isinstance(item, dict) and key is None and ("copy" in item or "replace" in item):
                # Identified by its place in the list, which moves when the
                # list is edited: given an id, as the editor's files need one.
                key = free_key(project, slug(item.get("name") or item.get("copy") or item.get("replace") or "duelist"))
                messages.append(f"{where} has no id; the editor gives it \"{key}\" (a save's record of it "
                                "under its place in the list does not follow)")
            e = _read_entry(project, item, key, origin, where, messages)
            if e is None:
                project.roster_kept.append(item)
                continue
            if any(o.key == e.key for o in project.roster):
                messages.append(f"{where}: {e.key} is already taken; the game leaves this one out")
            project.roster.append(e)
            _read_portrait(project, e, folder, messages)
    if folder is None:
        return
    directory = Path(folder) / "duelists"
    if not directory.is_dir():
        return
    from .manifest import read_json
    for path in sorted(directory.glob("*.json"), key=lambda p: p.name.encode("utf-8")):
        key = path.name[:-5]
        rel = f"duelists/{path.name}"
        if not key:
            continue
        try:
            value = read_json(path)
        except (OSError, ValueError) as problem:
            messages.append(f"{rel}: {problem}; left as it is")
            continue
        e = _read_entry(project, value, key, "folder", rel, messages)
        if e is None:
            continue        # the file stays, untouched
        if not FILE_KEY_RE.match(key):
            messages.append(f"{rel}: an id the editor's files cannot use; left as it is")
            continue
        if any(o.key == e.key for o in project.roster):
            messages.append(f"{rel}: {e.key} is already taken; the game leaves this one out")
        project.roster.append(e)
        project.roster_owned.add(rel)
        _read_portrait(project, e, folder, messages)


def read_pool_folders(project, folder, messages: list):
    """decks/ and drops/ beside mod.json, after the manifest's tables, as
    tables.c reads them: a file to a duelist, named for this mod's duelist
    of that id, else for a duelist as any entry names one, or "all". A file
    the editor reads it rewrites (a copy's back in its file, a disc duelist's
    in mod.json); one naming nobody here, or holding a fixed deck, stays."""
    from .manifest import POOL_ALIASES, _json_bool, _read_pool, read_json, same_all
    if folder is None:
        return
    for kind in ("drops", "decks"):
        directory = Path(folder) / kind
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json"), key=lambda p: p.name.encode("utf-8")):
            name = path.name[:-5]
            rel = f"{kind}/{path.name}"
            if not name or len(name) >= 64:
                continue
            own = find(project, name)
            if own is not None:
                target = [own.base] if own.replace else [own]
            elif same_all(name):
                target = subjects(project)
            else:
                found = named(project, name)
                if found is None:
                    messages.append(f"{rel}: no duelist of that name here; left as it is")
                    continue
                target = [found]
            try:
                body = read_json(path)
            except (OSError, ValueError) as problem:
                messages.append(f"{rel}: {problem}; left as it is")
                continue
            if kind == "decks" and isinstance(body, dict) and _json_bool(body.get("fixed"), False):
                if len(target) == 1 and not isinstance(target[0], int):
                    from . import fixed_decks
                    fixed_decks.read_file(project, rel, target[0], body, messages)
                    project.roster_owned.add(rel)
                    continue
                messages.append(f"{rel}: a fixed deck; left as it is (the editor edits fixed decks of the disc's "
                                "duelists in mod.json)")
                continue
            if kind == "decks":
                _read_pool(project, rel, target, "deck", body, messages)
            elif not isinstance(body, dict):
                messages.append(f"{rel}: an object of pools (pow, bcd, tec); left as it is")
                continue
            else:
                for pool_name, pool_body in body.items():
                    pool = POOL_ALIASES.get("".join(c for c in pool_name.lower() if c.isalnum()))
                    if pool in (None, "deck"):
                        messages.append(f"{rel} \"{pool_name}\": the pools are pow, bcd and tec; left out")
                        continue
                    _read_pool(project, f"{rel} \"{pool_name}\"", target, pool, pool_body, messages)
            project.roster_owned.add(rel)


# --- writing ----------------------------------------------------------------------------------

def _base_value(e: RosterDuelist):
    """How the entry names its base: as it was written while that still
    names it, else by the disc's name."""
    field = "replace" if e.replace else "copy"
    if e.written is not None:
        value = e.written.get(field)
        if isinstance(value, (str, int)) and not isinstance(value, bool) and duelist_named(value) == e.base:
            return value
    return DUELIST_NAMES[e.base]


def entry(e: RosterDuelist, with_id: bool) -> dict:
    """The entry as the game reads it: its id when it is in a list, then
    copy or replace, name, slot and portrait, then the rest as written. One
    that says what it said when read is written as it was."""
    out = {}
    if with_id:
        out["id"] = e.key
    out["replace" if e.replace else "copy"] = _base_value(e)
    if e.name:
        out["name"] = e.name
    if e.slot is not None and not e.replace:
        out["slot"] = e.slot
    if e.portrait_path:
        out["portrait"] = e.portrait_path
    for k, v in e.extra.items():
        out.setdefault(k, v)
    if e.written is not None and json.dumps(e.written, sort_keys=True) == json.dumps(out, sort_keys=True):
        return _copy.deepcopy(e.written)       # its own order of keys
    return out


def manifest_value(project):
    """What mod.json's "duelists" holds: the file it names, or the list of
    the entries written in it (and those the editor kept as written); None
    when there is nothing to write there."""
    if project.roster_file is not None:
        return project.roster_file
    if getattr(project, "roster_raw", None) is not None:
        return project.roster_raw
    listed = [entry(e, True) for e in entries(project) if e.origin == "manifest"]
    listed += list(getattr(project, "roster_kept", []))
    return listed or None


def portrait_file(e: RosterDuelist) -> str:
    return e.portrait_path or f"portraits/{e.key}.png"


def files(project, decks: dict, drops: dict) -> dict:
    """{path in the mod: bytes} of the roster: each folder entry's
    duelists/<id>.json, each face, each copy's decks/ and drops/ files
    (`decks` and `drops` hold the bodies by entry, manifest._pool_tables), and
    the file mod.json's "duelists" names."""
    from .manifest import dumps
    out = {}
    for e in entries(project):
        if e.origin == "folder":
            out[f"duelists/{e.key}.json"] = dumps(entry(e, False)).encode("utf-8")
        if e.portrait is not None:
            out[portrait_file(e)] = e.portrait
        if e.copy and e in decks:
            out[f"decks/{e.key}.json"] = dumps(decks[e]).encode("utf-8")
        if e.copy and e in drops:
            out[f"drops/{e.key}.json"] = dumps(drops[e]).encode("utf-8")
    if project.roster_file is not None and not getattr(project, "roster_file_unread", False):
        listed = [entry(e, True) for e in entries(project) if e.origin == "file"]
        listed += list(getattr(project, "roster_kept", []))
        out[project.roster_file] = dumps(listed).encode("utf-8")
    return out


def write(project, folder, decks: dict, drops: dict):
    """The roster's files into the mod folder; a file the roster was read
    from and now has no use for (a duelist removed, renamed, a pool back as
    its base's) goes."""
    folder = Path(folder)
    made = files(project, decks, drops)
    for rel in sorted(getattr(project, "roster_owned", set()) - set(made)):
        target = folder / rel
        if target.is_file():
            target.unlink()
    for rel, blob in made.items():
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_bytes() != blob:
            target.write_bytes(blob)
    project.roster_owned = set(made)


def owned(project, rel) -> bool:
    """Whether a file of the folder the mod was read from is the roster's to
    write (save_mod does not copy it: it writes it afresh)."""
    return str(rel).replace("\\", "/") in getattr(project, "roster_owned", set())


# --- checks ----------------------------------------------------------------------------------

def check(project, out: list):
    """What the game would refuse, or place other than meant (validate)."""
    from . import duelist_rules, fixed_decks
    from .gamedata import DECK_POOL_MIN_CARDS, POOL_LABELS
    from .validate import Issue
    keys = {}
    for e in entries(project):
        keys.setdefault(e.key.lower(), []).append(e)
    places = placement(project)
    for e in entries(project):
        where = f"{shown_name(project, e if e.copy else e.base)} ({e.key})"
        target = (e if e.copy else e.base, None)
        add = lambda level, message: out.append(Issue(level, "Duelists", where, message, target))  # noqa: E731
        if not FILE_KEY_RE.match(e.key) or len(e.key) > KEY_MAX:
            add("error", f"the id {e.key!r} cannot name a file (up to {KEY_MAX} letters, no / \\ : * ? \" < > |)")
        if len(keys[e.key.lower()]) > 1:
            add("error", f"the id {e.key} is used {len(keys[e.key.lower()])} times; the game keeps the first "
                         "and leaves the rest out (a file system that ignores case keeps only one file)")
        if not 1 <= e.base < DUELIST_COUNT:
            add("error", "copies no disc duelist (1 to 39)")
            continue
        if e.name and len(e.name) > NAME_MAX:
            add("warning", f"a name of {len(e.name)} letters: the game matches on the first {NAME_MAX}")
        if e.name and any(ord(c) < 32 for c in e.name):
            add("error", "a control character in its name")
        if "slot" in e.extra:
            slot = e.extra["slot"]
            if e.replace:
                add("warning", "a replacement keeps its duelist's place; its slot is left out")
            else:
                add("error", f"slot {slot!r} is no id from {FIRST_SLOT} to {LAST_SLOT}; it takes the first free place")
        if e.copy and isinstance(e.slot, int):
            if not FIRST_SLOT <= e.slot <= LAST_SLOT:
                add("error", f"slot is an id from {FIRST_SLOT} to {LAST_SLOT}")
            elif places.get(e) != e.slot and places.get(e) is not None:
                rival = next((o for o, s in places.items() if s == e.slot and o is not e), None)
                add("warning", f"slot {e.slot} is taken by {shown_name(project, rival) if rival else 'another'}; "
                               f"this one goes to {places[e]} ({where_text(places[e])})")
        if e.copy and places.get(e) is None and len(keys[e.key.lower()]) == 1:
            add("error", f"no room left: the grid holds ids up to {LAST_SLOT}")
        if e.portrait is not None and picture(e.portrait) is None:
            add("error", "its portrait is not a PNG the game can read")
        duelist_rules.check(project, e, add)
        if e.copy and e.pools is not None:
            for pool in POOLS:
                weights = {c: w for c, w in e.pools[pool].items() if w}
                if weights == {c: w for c, w in project.retail.pools[e.base][pool].items() if w}:
                    continue
                place = f"{where} {POOL_LABELS[pool]}"
                issue = lambda level, message: out.append(  # noqa: E731
                    Issue(level, "Duelists", place, message, (e, pool)))
                if any(c not in project.cards for c in weights):
                    issue("error", "names a card that does not exist")
                if any(w < 0 or w > 0xFFFF for w in weights.values()):
                    issue("error", "a weight is a whole number, 0 to 65535")
                if pool == "deck" and fixed_decks.deck_of(project, e) is None and len(weights) < DECK_POOL_MIN_CARDS:
                    issue("error", f"a deck is dealt from at least {DECK_POOL_MIN_CARDS} cards; it has {len(weights)} "
                                   "(the game deals its base's deck instead)")
                elif pool != "deck" and not weights:
                    issue("error", "no card would be left to win (the game keeps its base's)")
                elif sum(weights.values()) != 2048:
                    issue("error", f"the weights add up to {sum(weights.values())}, not 2048 (Scale to 2048 fixes it)")


def where_text(slot) -> str:
    return where(slot)
