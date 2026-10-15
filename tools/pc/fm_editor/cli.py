"""The editor's command line.

    python tools/pc/fm_editor [--game <folder or .bin>] [--mod <mod folder>]
        the editor's window (the game is found where the port looks for it)

    python tools/pc/fm_editor check <mod folder> [--game <folder or .bin>]
        open the mod over the retail tables, list what the loader would
        complain about, and print the mod.json the editor would save

    python tools/pc/fm_editor import <modified .bin, folder, SLUS_014.11, or an old recomp's .ygomods> -o <mod folder>
                             [--wa <modified WA_MRG.MRG>] [--game <retail>] [--id <mod id>]
        turn a community mod's modified game files into a port mod (what
        differs from retail); what cannot be carried over is reported.
        Importing a modified game is experimental and not supported yet
"""
from __future__ import annotations

import argparse
import sys

from . import disc, gamedata, importer, manifest, validate


def load_retail(game):
    files = disc.load(game) if game else disc.find_game()
    if files is None:
        raise SystemExit("the game files were not found; name them with --game <folder or .bin>")
    return gamedata.load_game(files), files


def command_check(arguments) -> int:
    retail, files = load_retail(arguments.game)
    project, messages = manifest.open_mod(retail, arguments.mod)
    for message in messages:
        print(f"read: {message}")
    issues = validate.validate(project)
    for issue in issues:
        print(issue)
    if arguments.print:
        sys.stdout.write(manifest.dumps(manifest.build(project)))
    print(f"{len(validate.errors(issues))} errors, {len(issues) - len(validate.errors(issues))} warnings "
          f"(game files: {files.source})", file=sys.stderr)
    return 1 if validate.errors(issues) else 0


def command_import(arguments) -> int:
    from pathlib import Path
    from .importer import slug
    retail, retail_files = load_retail(arguments.game)
    if arguments.modded.lower().endswith(".ygomods"):
        from . import ygomods
        try:
            project, report = ygomods.import_package(retail, retail_files.wa, arguments.modded,
                                                     arguments.id or slug(arguments.modded),
                                                     Path(arguments.modded).stem)
        except ygomods.PackageError as problem:
            raise SystemExit(f"import: {problem}")
        manifest.save_mod(project, arguments.output)
    else:
        try:
            modded = disc.load_pair(arguments.modded, arguments.wa) if arguments.wa else disc.load(arguments.modded)
        except (disc.GameFilesError, OSError) as problem:
            raise SystemExit(f"import: {problem}")
        source = Path(arguments.modded).resolve()
        if source.is_file() and source.suffix.lower() in (".bin", ".iso", ".img"):
            name = source.stem
        else:
            name = source.parent.name if source.is_file() else source.name
        try:
            result = importer.import_modded(retail_files, modded, arguments.id or slug(name), name)
        except ValueError as problem:
            raise SystemExit(f"import: {problem}")
        importer.save(result, arguments.output)
        project, report = result.project, result.report
    for line in report:
        print(line)
    print(f"wrote {Path(arguments.output) / 'mod.json'}", file=sys.stderr)
    # What the loader would refuse, as "check" says it (the GUI will not save it).
    errors = validate.errors(validate.validate(project))
    for issue in errors:
        print(issue, file=sys.stderr)
    if errors:
        print(f"{len(errors)} errors: the loader will leave those rules out; fix them in the editor", file=sys.stderr)
    return 1 if errors else 0


def build_parser():
    parser = argparse.ArgumentParser(prog="fm_editor", description="FM Editor: mods for the Forbidden Memories port")
    parser.add_argument("--version", action="store_true", help="show the editor build and supported mod API")
    parser.add_argument("--game", help="the game: a folder with SLUS_014.11 and DATA/WA_MRG.MRG, or the .bin")
    parser.add_argument("--mod", help="a mod folder to open")
    commands = parser.add_subparsers(dest="command")
    check = commands.add_parser("check", help="validate a mod folder against the retail tables")
    check.add_argument("mod")
    check.add_argument("--game", default=argparse.SUPPRESS,     # so a --game before "check" counts too
                       help="the game: a folder with SLUS_014.11 and DATA/WA_MRG.MRG, or the .bin")
    check.add_argument("--print", action="store_true", help="print the mod.json the editor would write")
    imp = commands.add_parser("import", help="turn a modified game into a port mod (experimental for a .bin, folder or SLUS_014.11)")
    imp.add_argument("modded", help="the modified game: a .bin, a folder or its SLUS_014.11; or an old recomp's .ygomods package, converted one way")
    imp.add_argument("-o", "--output", required=True, help="the mod folder to write")
    imp.add_argument("--wa", help="the modified WA_MRG.MRG, when the first argument is SLUS_014.11 alone")
    imp.add_argument("--game", help="the retail game (default: found where the port looks)")
    imp.add_argument("--id", help="the mod id (default: from the file name)")
    smoke = commands.add_parser("self-test", help="check the GUI and export using synthetic game files (needs a display)")
    smoke.add_argument("--output", required=True, help="JSON result file, also on Windows without a console")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.version:
        from .build_info import description
        print(description())
        return 0
    if arguments.command == "self-test":
        from .self_test import run
        return run(arguments.output)
    if arguments.command == "check":
        return command_check(arguments)
    if arguments.command == "import":
        return command_import(arguments)
    from .app import main as window
    return window(arguments.game, arguments.mod)
