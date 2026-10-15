"""python tools/pc/fm_editor [command ...]: see cli.py."""
import sys
from pathlib import Path

if not __package__:
    # Run as a folder: make "fm_editor" (and text_listing beside it) importable.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fm_editor.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
