"""Which game a mod needs: its "min_api", from what its mod.json uses.

The port refuses a mod whose "min_api" is past its own mod API (manager.c
Mods_Compatible: "needs a newer game: mod API N, this one has M"), data mods
too. A game older than a key or value a mod uses would instead leave that
part out, with at most an "unknown key" note, and play the rest: a
half-working mod. So the editor writes, on save, the lowest API that has
every feature the mod uses, never lowering a "min_api" the author set
higher. notes/modding.md ("Which game a mod needs") lists the same features.

HOST_API is src/pc/mods/mod_types.h's MEMORIES_MOD_API. The packaged editor
has no source tree to read it from, so it is a constant here and
tests/test_compat.py holds it to that header.
"""
from __future__ import annotations

from pathlib import Path

from .gamedata import FRAME_COLOR_NAMES, TYPE_MAGIC
from .model import type_named

HOST_API = 16

# The release each mod API first shipped in, for the hints. An API past the
# last listed is newer than every release.
RELEASES = {9: "v0.2.0", 10: "v0.2.1-preview.1", 11: "v0.3.0", 12: "v0.3.0"}

# tables.c read_limits: what v0.2.1-preview.1 and older know.
OLD_LIMITS = ("stats", "attack", "defense", "life_points", "two_player", "starchips", "chest", "free_duel_record",
              "two_player_record")
# The values a game of API 12 and older leaves out.
API_13_LIMITS = ("card_drops",)


def release_text(api: int) -> str:
    """The games that run a mod of this API, in words."""
    if api in RELEASES:
        return f"the game {RELEASES[api]} or newer"
    last = max(RELEASES)
    if api > last:
        return f"a game newer than {RELEASES[last]}"
    return f"the game {RELEASES[min(RELEASES)]} or newer"


def _entries(value):
    """The objects of a list key (a file name or anything else: none)."""
    return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []


def external_packs(name: str, project=None) -> tuple:
    """(pack list, problem) for packs.c's external list or wrapper object.

    Read staged files before the source folder, just as Save writes them.
    Failure is explicit: an unreadable file cannot establish compatibility.
    The original file and manifest reference are never changed.
    """
    from .overlaps import parse
    # Match paths.c Paths_Contained, including its rejection of backslashes
    # and empty/dot components even on Windows.
    parts = name.split("/")
    if not name or "\\" in name or name.startswith("/") or name[1:2] == ":" or \
            any(part in ("", ".", "..") for part in parts):
        return [], f"packs file {name!r} must be inside the mod"
    try:
        files = getattr(project, "files", {})
        if name in files:
            blob = files[name]
        else:
            source = getattr(project, "source_dir", None)
            if source is None:
                return [], f"packs file {name!r} has no source folder"
            source = Path(source).resolve()
            path = source.joinpath(*parts).resolve()
            if not path.is_relative_to(source):
                return [], f"packs file {name!r} must be inside the mod"
            blob = path.read_bytes()
        text = blob.decode("utf-8", errors="surrogateescape")
        value = parse(text)
    except (OSError, ValueError) as problem:
        return [], f"cannot read packs file {name!r}: {problem}"
    if value is None and text.strip() != "null":     # overlaps.parse: what json.c cannot read
        return [], f"packs file {name!r} is not valid JSON"
    if isinstance(value, dict):
        value = value.get("packs", [])
    if not isinstance(value, list):
        return [], f"packs file {name!r} must contain a pack list or an object with a packs list"
    return value, None


def problems(manifest: dict, project=None) -> list:
    """Reasons the editor cannot determine all feature requirements."""
    value = manifest.get("packs")
    if isinstance(value, str):
        _, problem = external_packs(value, project)
        return [problem] if problem else []
    return []


def _has_key(value, key: str) -> bool:
    """Whether `key` is a key of any object in value, at any depth."""
    if isinstance(value, dict):
        return key in value or any(_has_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_has_key(item, key) for item in value)
    return False


def _has_action(value, action: str) -> bool:
    """Whether any object in value, at any depth, has "action": action."""
    if isinstance(value, dict):
        return value.get("action") == action or any(_has_action(item, action) for item in value.values())
    if isinstance(value, list):
        return any(_has_action(item, action) for item in value)
    return False


def _type_of(value) -> int:
    if isinstance(value, bool):
        return -1
    if isinstance(value, int):
        return value
    return type_named(value) if isinstance(value, str) else -1


def _copy_changes_kind(project, entry: dict) -> bool:
    """A copy whose "type" v0.2.0 left out (cards.c add_entry): a copy of a
    monster made a non-monster, or a non-monster made any other type."""
    if project is None or "type" not in entry:
        return False
    base = project.resolve(entry.get("copy"))
    card = project.cards.get(base) if base else None
    new = _type_of(entry["type"])
    if card is None or new < 0:
        return False
    if card.type < TYPE_MAGIC:
        return new >= TYPE_MAGIC
    return new != card.type


def features(manifest: dict, project=None) -> list:
    """[(api, what)] for each feature of the manifest newer than API 9 (the
    oldest any data mod needs to say). `project`, when given, tells a copy's
    base's type."""
    out = []
    add = lambda api, what: out.append((api, what))
    # --- API 10: v0.2.1-preview.1 -------------------------------------------
    if "card_text_colors" in manifest:
        add(10, "card text colors (\"card_text_colors\")")
    for entry in _entries(manifest.get("cards")):
        if "monster_effects" in entry:
            add(10, "monster effects")
        if "trap_threshold" in entry:
            add(10, "a card's own trap threshold (\"trap_threshold\")")
        if "copy" in entry:
            if _copy_changes_kind(project, entry):
                add(10, "an added card of another kind than its base")
            if isinstance(entry.get("model"), str) or isinstance(entry.get("effect"), str):
                add(10, "an added card's \"model\" or \"effect\" by name")
        # --- API 11 ---------------------------------------------------------
        if "tags" in entry:
            add(11, "card tags")
        frame = entry.get("frame")
        if isinstance(frame, str) and frame.lower() in (name.lower() for name in FRAME_COLOR_NAMES):
            add(11, f"the frame name \"{frame}\"")
        for effect in _entries(entry.get("monster_effects")):
            if "for_each" in effect:
                add(11, "a monster effect's \"for_each\"")
    for entry in _entries(manifest.get("equips")):
        if "bonus_attack" in entry or "bonus_defense" in entry:
            add(10, "separate equip ATK and DEF boosts")
    pack_list = manifest.get("packs")
    if isinstance(pack_list, str):
        pack_list, _ = external_packs(pack_list, project)
    for entry in _entries(pack_list):
        if "image_style" in entry:
            add(10, "a pack's \"image_style\"")
    # --- API 11 -------------------------------------------------------------
    for key, what in (("assets", "named game images (\"assets\")"), ("ui", "duel screen layout (\"ui\")"),
                      ("card_layout", "the card layout (\"card_layout\")"),
                      ("palette_ramps", "text color ramps (\"palette_ramps\")")):
        if key in manifest:
            add(11, what)
    title, menu = manifest.get("title"), manifest.get("menu")
    if isinstance(title, dict) and "images" in title:
        add(11, "title pictures (\"images\")")
    if _has_key(title, "scale") or _has_key(menu, "scale"):
        add(11, "a title or menu \"scale\"")
    for entry in _entries(manifest.get("fusions")):
        if entry.get("remove") == "all":
            add(11, "removing all fusions")
    for entry in _entries(manifest.get("rituals")):
        origin = entry.get("tributes_from")
        if isinstance(origin, str) and origin.lower() != "field":
            add(11, "ritual tributes from the hand")
        tributes = entry.get("tributes")
        if isinstance(tributes, list) and len(tributes) != 3:
            add(11, "a ritual of other than three tributes")
    limits = manifest.get("limits")
    if isinstance(limits, dict):
        newer = sorted(key for key in limits if key not in OLD_LIMITS and key not in API_13_LIMITS)
        if newer:
            add(11, "the values " + ", ".join(newer))
    # --- API 13 -------------------------------------------------------------
    if isinstance(limits, dict) and "card_drops" in limits:
        add(13, "the cards a win deals locked (\"limits\" \"card_drops\")")
    # --- API 14 -------------------------------------------------------------
    if "tower" in manifest:
        add(14, "a tower (\"tower\")")
    for entry in _entries(manifest.get("duelists")):
        if "tower_only" in entry:
            add(14, "a duelist of the tower's alone (\"tower_only\")")
        if isinstance(entry.get("unlock"), dict) and "tower" in entry["unlock"]:
            add(14, "a duelist's \"unlock\" \"tower\"")
    for part in (title, menu):
        if _has_action(part, "tower"):
            add(14, "a menu item's action \"tower\"")
    # --- API 15 -------------------------------------------------------------
    if "card_types" in manifest:
        add(15, "custom card types (\"card_types\")")
    # --- API 16 -------------------------------------------------------------
    if "attributes" in manifest:
        add(16, "mod-defined card attributes (\"attributes\")")
    return out


def required(manifest: dict, project=None) -> tuple:
    """(the lowest API that has every feature, [what needs that API]); 0 and
    [] when an older game has them all."""
    found = features(manifest, project)
    if not found:
        return 0, []
    api = max(level for level, _ in found)
    reasons = []
    for level, what in found:
        if level == api and what not in reasons:
            reasons.append(what)
    return api, reasons


def stamp(manifest: dict, project=None) -> dict:
    """Raise the manifest's "min_api" to what it uses, in place: never
    lowered, and left alone when it is not a whole number (validate.py
    says so). A "min_api" it gains goes after the mod's name and the like."""
    api, _ = required(manifest, project)
    written = manifest.get("min_api")
    if not api or (written is not None and (isinstance(written, bool) or not isinstance(written, int))):
        return manifest
    if written is not None:
        if written < api:
            manifest["min_api"] = api
        return manifest
    items = list(manifest.items())
    at = next((i for i, (key, _) in enumerate(items) if key not in ("id", "name", "version", "author",
                                                                     "description")), len(items))
    items.insert(at, ("min_api", api))
    manifest.clear()
    manifest.update(items)
    return manifest
