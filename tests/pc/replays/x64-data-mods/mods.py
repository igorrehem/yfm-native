"""The data mods of this replay, made in the play's folder from the
repository and the player's disc (a texture pack's images are the game's,
so they are never kept here): the card-pack example (two cards with their
own fusion) and a texture pack of the screens' sheets with every color
turned around. tools/pc/replay.py calls make() before the game starts, when
playing and when recording (`record --mods`), with the repository's root:
this file may be in a .yfmreplay unpacked anywhere."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

CARDS = "example-cards"
TEXTURES = "x64-gate-textures"


def make(folder: Path, root: Path) -> list[str]:
    """The mods, in `folder`, from the repository at `root`; returns their
    ids, which the game is to turn on."""
    from PIL import Image, ImageOps
    folder.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(folder / CARDS, ignore_errors=True)
    shutil.copytree(root / "examples/mods/card-pack", folder / CARDS)
    pack = folder / TEXTURES
    shutil.rmtree(pack, ignore_errors=True)
    extract = subprocess.run([sys.executable, str(root / "tools/pc/extract_images.py"), "--data",
                              str(root / "game/DATA"), "--out", str(pack / "images"), "sheets"],
                             cwd=root, capture_output=True, text=True, errors="replace")
    if extract.returncode:
        raise RuntimeError(f"extract_images.py could not take the screens' sheets from {root / 'game/DATA'} "
                           f"(exit {extract.returncode}):\n{(extract.stderr or extract.stdout).strip()}")
    for png in sorted((pack / "images").rglob("*.png")):
        image = Image.open(png).convert("RGBA")
        red, green, blue, alpha = image.split()
        turned = ImageOps.invert(Image.merge("RGB", (blue, red, green)))
        Image.merge("RGBA", (*turned.split(), alpha)).save(png)
    (pack / "mod.json").write_text(json.dumps({"id": TEXTURES, "name": "x64 gate textures", "enabled": True,
                                               "textures": "images"}, indent=4), encoding="utf-8")
    return [CARDS, TEXTURES]
