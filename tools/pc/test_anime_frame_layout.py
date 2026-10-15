#!/usr/bin/env python3
"""anime_frame_layout.build: the frame styles and rules a build and a patch write.

    python3 tools/pc/test_anime_frame_layout.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anime_frame_layout as L  # noqa: E402


def frames(*kinds):
    return {k: {"image": f"textures/anime_frame_{k}.png", "width": 140, "height": 197} for k in kinds}


def rule_styles(layout):
    return [(r["class"], r["style"]) for r in layout["frame_for"]]


def main():
    # The HD mod's pictures: monster, magic, trap, orange. Ritual spells green, effect monsters orange.
    layout, settings = L.build(frames("monster", "magic", "trap", "orange"))
    assert settings == []
    assert set(layout["frame_styles"]) == {"gold", "green", "pink", "orange"}
    assert layout["frame_styles"]["green"]["hand_color"] == "green"
    assert layout["default_style"] == "gold"
    assert ("ritual_spell", "green") in rule_styles(layout)
    assert ("effect_monster", "orange") in rule_styles(layout)
    # Every rule names a style that exists.
    for kinds in (("monster", "magic", "trap", "orange"), ("monster", "magic", "trap"),
                  ("monster", "magic", "trap", "ritual", "orange"), ("monster",)):
        layout, _ = L.build(frames(*kinds))
        for rule in layout["frame_for"]:
            assert rule["style"] in layout["frame_styles"], (kinds, rule)
    # No orange picture: effect monsters are plain monsters, no rule for them.
    layout, _ = L.build(frames("monster", "magic", "trap"))
    assert all(r["class"] != "effect_monster" for r in layout["frame_for"])
    # A ritual picture: a sub-option, off, before the green rule; the green rule stays after it.
    layout, settings = L.build(frames("monster", "magic", "trap", "ritual"))
    assert [s["key"] for s in settings] == ["ritual_own_frame"] and settings[0]["default"] == 0
    rules = layout["frame_for"]
    assert rules[0] == {"class": "ritual_spell", "style": "blue", "setting": "ritual_own_frame"}
    assert rules[1] == {"class": "ritual_spell", "style": "green"}
    assert layout["frame_styles"]["blue"]["hand_color"] == "blue"
    print("anime_frame_layout: ok")


if __name__ == "__main__":
    main()
