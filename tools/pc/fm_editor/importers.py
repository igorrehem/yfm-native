"""The window's File > Import entries."""
from __future__ import annotations

from pathlib import Path
from tkinter import messagebox

from . import disc, file_dialogs, importer, settings, ygomods
from .importer import slug


def _failed(app, problem: Exception):
    """Anything the importer did not expect, said in a window: a program
    built --windowed has no console for the traceback."""
    messagebox.showerror("Import", f"The import stopped: {type(problem).__name__}: {problem}", parent=app)


def ask_modded_files(app):
    """A modified game: its .bin, or its SLUS_014.11 (WA_MRG.MRG found in
    DATA/ beside it or asked for)."""
    path = file_dialogs.askopenfilename(
        parent=app, title="The modified game: its .bin disc image, or its SLUS_014.11",
        filetypes=[("Disc image or executable", "*.bin *.iso *.img SLUS_014.11 *.11"), ("All files", "*.*")])
    if not path:
        return None, None
    path = Path(path)
    try:
        if path.suffix.lower() in (".bin", ".iso", ".img"):
            return disc.load(path), path.stem
        wa = path.parent / "DATA" / "WA_MRG.MRG"
        if not wa.is_file():
            wa = path.parent / "WA_MRG.MRG"
        if not wa.is_file():
            chosen = file_dialogs.askopenfilename(parent=app, title="The modified game's WA_MRG.MRG",
                                                  filetypes=[("WA_MRG.MRG", "*.MRG"), ("All files", "*.*")])
            if not chosen:
                return None, None
            wa = Path(chosen)
        return disc.load_pair(path, wa), path.parent.name
    except (disc.GameFilesError, OSError) as problem:
        messagebox.showerror("Import", str(problem), parent=app)
        return None, None


def import_modded_game(app):
    if not app.need_game() or not app.confirm_discard():
        return
    files, name = ask_modded_files(app)
    if files is None:
        return
    app.config(cursor="watch")
    app.update()
    try:
        result = importer.import_modded(app.files, files, slug(name), name)
    except ValueError as problem:
        messagebox.showerror("Import", str(problem), parent=app)
        return
    except Exception as problem:
        _failed(app, problem)
        return
    finally:
        app.config(cursor="")
    app.set_project(result.project)
    app.changed()
    app.say(f"Imported {files.source}: save it to write the mod folder.")
    app.report("Import report", "Compared with your retail game:\n\n" + "\n".join("- " + line for line in result.report)
               + "\n\nThe report is saved with the mod as import-report.txt.")


def import_ygomods(app):
    if not app.need_game() or not app.confirm_discard():
        return
    path = file_dialogs.askopenfilename(parent=app, title="An old recomp's .ygomods package, to convert",
                                        filetypes=[(".ygomods package", "*.ygomods"), ("All files", "*.*")])
    if not path:
        return
    try:
        project, report = ygomods.import_package(app.retail, app.files.wa, path, slug(path), Path(path).stem)
    except ygomods.PackageError as problem:
        messagebox.showerror("Import", str(problem), parent=app)
        return
    except Exception as problem:
        _failed(app, problem)
        return
    app.set_project(project)
    app.changed()
    app.say(f"Converted {path}: save it to write the mod folder.")
    app.report("Import report", "Converted once from the old recomp's package (the port does not read .ygomods; "
               "check the result in the game):\n\n" + "\n".join("- " + line for line in report)
               + "\n\nThe report is saved with the mod as import-report.txt.")


def install(app):
    # Importing a PS1 ROM hack is experimental and not supported yet: its
    # entry shows only with "experimental_rom_import": true in settings.json.
    if settings.load().get("experimental_rom_import") is True:
        app.add_import("Import a modified game (.bin or SLUS_014.11, experimental)...",
                       lambda: import_modded_game(app))
    app.add_import("Convert an old recomp's .ygomods package (one way)...", lambda: import_ygomods(app))
