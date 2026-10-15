"""The anime frame's frame styles and the rules that pick them (card_layout in mod.json).

A frame STYLE is a picture and the color its small card in the hand wears:
  "frame_styles": {"green": {"image": "textures/anime_frame_magic.png", "hand_color": "green", ...}}
A RULE says which cards wear which style, the first that applies wins:
  "frame_for": [{"class": "ritual_spell", "style": "green"}, ...]
  a rule may name a "class" (monster, effect_monster, spell, equip, ritual_spell, trap),
  a "tag" (a cards mod's "tags"), and a "setting" (a bool the mod declares, so a player can
  switch the rule on in the Mods window); one that names none applies to every card.
"default_style" is worn by a card no rule picks.
Both sizes of the card follow the style: the card view draws its picture, the hand paints its
frame in its color. See notes/modding.md, "Card layout".

Used by hd_assets_pack.py (a build) and anime_frame_patch.py (an already built mod).
"""

# The PNG a kind of frame comes from -> the style it is, named by color (the color its hand card wears).
STYLE_OF_KIND = {"monster": "gold", "magic": "green", "trap": "pink", "ritual": "blue", "orange": "orange"}

RITUAL_SETTING = {
    "key": "ritual_own_frame", "label": "Ritual spells: own frame", "type": "bool", "default": 0,
    "description": "Ritual spells wear their own (blue) frame instead of the green spell frame."}

# (class, the style it wears, the style it falls back to when that has no picture)
CLASS_RULES = (("effect_monster", "orange"), ("spell", "green"), ("equip", "green"), ("trap", "pink"),
               ("monster", "gold"))


def build(frames):
    """frames: {"monster": {"image", "width", "height"}, ...}, by the kind of PNG (STYLE_OF_KIND).
    Returns (card_layout keys, mod settings to add)."""
    styles = {}
    for kind, name in STYLE_OF_KIND.items():
        if kind in frames:
            styles[name] = dict(frames[kind], hand_color=name)
    rules = []
    settings = []
    if "blue" in styles:   # a ritual picture of its own: a sub-option, off, ritual spells stay green
        rules.append({"class": "ritual_spell", "style": "blue", "setting": RITUAL_SETTING["key"]})
        settings.append(dict(RITUAL_SETTING))
    rules.append({"class": "ritual_spell", "style": "green" if "green" in styles else "gold"})
    for cls, name in CLASS_RULES:
        if name in styles or name == "gold":
            rules.append({"class": cls, "style": name})
        else:
            rules.append({"class": cls, "style": "gold"})
    if "orange" not in styles:   # no orange picture: effect monsters wear the monster frame like any monster
        rules = [r for r in rules if r["class"] != "effect_monster"]
    return {"frame_styles": styles, "frame_for": rules, "default_style": "gold"}, settings
