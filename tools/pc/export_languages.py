#!/usr/bin/env python3
"""Write the official languages' text packs (languages/*.txt) off the PAL discs.

    python3 tools/pc/export_languages.py --discs game/pal
    python3 tools/pc/export_languages.py --discs game/pal --check
    python3 tools/pc/export_languages.py --discs languages --check

Game > Language reads each European language's text from languages/<name>.txt
beside the program (en-eu, fr, de, it, es): the listing the port itself makes
of the PAL disc's language pack (src/pc/text/pal_text.c), in the format a
translation mod's text is written in (notes/translation.md). This runs a built
game with MEMORIES_EXPORT_LANGUAGES, which writes those listings and exits, so
the packs are the port's own reading of the discs, byte for byte.

--discs is the folder of the PAL disc images (.bin or .cue, any names; each
language is read off its own country's disc, SLES-03947 to 03951). --check
compares instead of writing: against the discs, it says whether the packs in
--out are what the discs give; pointed at the packs themselves, it says the
port reads them back unchanged."""
import argparse, filecmp, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NAMES = ("en-eu", "fr", "de", "it", "es")


def default_executable():
    for build in ("tmp/pc/game32", "tmp/pc/win32"):
        for name in ("memories-pc.exe", "memories-pc"):
            path = os.path.join(ROOT, build, name)
            if os.path.exists(path):
                return path
    return os.path.join(ROOT, "tmp/pc/game32/memories-pc")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--discs", default=os.path.join(ROOT, "game/pal"), help="folder of the PAL discs (game/pal)")
    parser.add_argument("--out", default=os.path.join(ROOT, "languages"), help="the packs' folder (languages)")
    parser.add_argument("--exe", default=default_executable(), help="a built game (tmp/pc/game32)")
    parser.add_argument("--check", action="store_true", help="compare with --out; write nothing")
    options = parser.parse_args()
    if not os.path.isdir(options.discs):
        parser.error(f"{options.discs} is not a folder")
    with tempfile.TemporaryDirectory() as written:
        command = [os.path.abspath(options.exe)]
        if command[0].endswith(".exe") and sys.platform != "win32":
            command = ["wine"] + command
        environment = dict(os.environ, MEMORIES_LANGUAGES_DIR=os.path.abspath(options.discs),
                           MEMORIES_EXPORT_LANGUAGES=written)
        result = subprocess.run(command, env=environment, capture_output=True, text=True)
        print(result.stdout, end="")
        if result.returncode:
            sys.exit(f"export_languages: {options.exe} exited {result.returncode}\n{result.stderr}")
        if options.check:
            differ = [name for name in NAMES
                      if not os.path.exists(os.path.join(options.out, f"{name}.txt")) or
                      not filecmp.cmp(os.path.join(written, f"{name}.txt"), os.path.join(options.out, f"{name}.txt"),
                                      shallow=False)]
            if differ:
                sys.exit(f"export_languages: differ from {options.out}: {', '.join(differ)}")
            print(f"export_languages: {options.out} is what {options.discs} gives, byte for byte")
            return
        os.makedirs(options.out, exist_ok=True)
        for name in NAMES:
            with open(os.path.join(written, f"{name}.txt"), "rb") as source:
                data = source.read()
            with open(os.path.join(options.out, f"{name}.txt"), "wb") as target:
                target.write(data)
        print(f"export_languages: wrote {len(NAMES)} packs to {options.out}")


if __name__ == "__main__":
    main()
