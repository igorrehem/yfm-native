"""Timings of the FM Editor's 3D board and map renders, every path a user
takes: the renders themselves (board_model.py, map_view.py), then, with a
display, the UI tab's Duel board page (opening it, switching fields, a
middle-button drag, the full render on release, choosing a part, a tint)
the Duel page and the Map tab, the canvas about 1600x960.

    python tools/pc/bench_board.py [--game game/] [--no-gui] [--slow N]

--slow N rasterizes everything N times over (a machine N times slower: the
page sees each frame take that long and lowers its drag resolution).
Under taskset -c 0 it has one core, as a small machine would. Times are
milliseconds: the median of a few runs, the worst in brackets."""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fm_editor import board_art as ba, board_model as bm, map_view  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ROWS = []


def row(name, times):
    times = [t * 1000 for t in times]
    ROWS.append((name, statistics.median(times), max(times)))
    print(f"{name:52} {statistics.median(times):8.1f}  ({max(times):.1f})", flush=True)


def timed(make, repeat=3):
    out = []
    for _ in range(repeat):
        start = time.perf_counter()
        make()
        out.append(time.perf_counter() - start)
    return out


def caches():
    for name in ("_BOARDS", "_PIECES", "_PICTURES", "_TABLES", "_SCENES"):
        for module in (bm, map_view):
            cache = getattr(module, name, None)
            if isinstance(cache, dict):
                cache.clear()


def renders(game: Path):
    wa = (game / "DATA" / "WA_MRG.MRG").read_bytes()
    data = ba.read(wa)
    project = SimpleNamespace(retail=SimpleNamespace(board=data))
    print("-- renders --")
    row("parse a field's board (cold)", timed(lambda: (caches(), bm.board(data, "forest"))))
    row("a field's pieces, decoded (cold)", timed(lambda: (caches(), bm.pieces_of(project, "forest"))))
    board, pieces = bm.board(data, "normal"), bm.pieces_of(project, "normal")
    for size in ((320, 240), (533, 320), (800, 480), (1600, 960)):
        row(f"render {size[0]}x{size[1]} (warm)", timed(lambda: bm.render(board, pieces, bm.CAMERA, size)))
    row("render 1600x960, a new field (cold)",
        timed(lambda: (caches(), bm.render(bm.board(data, "umi"), bm.pieces_of(project, "umi"), bm.CAMERA,
                                           (1600, 960))), 2))
    picture = bm.render(board, pieces, bm.CAMERA, (1600, 960))
    row("outline the floor at 1600x960", timed(lambda: bm.outline(picture, [p.key for p in ba.FLOOR], 3)))
    row("render_board 320x240 (Duel page, cold)",
        timed(lambda: (caches(), bm.render_board(project, "normal", None, (320, 240)))))
    try:
        from fm_editor import campaign_map as cm
        sector = cm.PACKAGES[0][1]
        model = map_view.model(wa, sector)
        camera = (1500, 0x400, 0x200, 0, 0)
        row("map_view.render 320x240 (Map tab)", timed(lambda: map_view.render(model, camera), 2))
        row("map_view.render 320x240 + spotlight", timed(lambda: map_view.render(model, camera, True), 2))
        row("map_view.render_top 640x480 (Map overview)",
            timed(lambda: map_view.render_top(model, (0, 0), 4000, (640, 480)), 2))
    except Exception as problem:            # noqa: BLE001 -- a disc without the map
        print("map:", problem)


def gui(game: Path, slow: int):
    import tkinter as tk
    from unittest import mock
    from fm_editor import settings
    from fm_editor.app import App
    import tempfile
    home = Path(tempfile.mkdtemp())
    mock.patch.object(settings, "path", lambda: home / "settings.json").start()
    if slow > 1:
        real = map_view.raster_steps

        def slowed(size, faces, vram, pixels, ids=None, step=map_view.STEP):
            for _ in range(slow - 1):       # the same work again, thrown away
                yield from real(size, faces, vram, list(pixels), None, step)
            yield from real(size, faces, vram, pixels, ids, step)
        map_view.raster_steps = slowed
    print(f"-- the page{' (x%d slower)' % slow if slow > 1 else ''} --")
    app = App(ask=False, autostart=False)
    app.geometry("2233x1200+0+0")
    app.update()
    app.start(str(game), None, False)
    app.update()
    tab = app.ui
    page = tab.pages["board"]
    shown = []
    real_show = page.show

    def show():
        real_show()
        shown.append((time.perf_counter(), page.terrain, getattr(page, "scale", 1)))
    page.show = show

    def until(done, limit=10.0, start=None, mark=None):
        """Tk's loop run until done() (a full picture up); the time from
        `start` to the first picture shown after `mark` and to done."""
        start = time.perf_counter() if start is None else start
        first = None
        mark = len(shown) if mark is None else mark
        while time.perf_counter() - start < limit:
            app.update()
            if first is None and len(shown) > mark:
                first = shown[mark][0] - start
            if done():
                break
            time.sleep(0.001)
        end = time.perf_counter() - start
        return (first if first is not None else end), end

    caches()
    start = time.perf_counter()
    app.notebook.select(tab)
    tab.page_name.set("board")
    tab.show_page()
    first, full = until(lambda: page.picture is not None and page.scale == 1 and page._job is None)
    row("open the Duel board page (first, cold)", [time.perf_counter() - start])
    print("canvas", page.canvas_size())
    blocked = []
    firsts, fulls = [], []
    for terrain in list(ba.TERRAINS[1:]) + ["normal"]:
        page.field.set(terrain)
        mark = len(shown)
        start = time.perf_counter()
        page.choose_field()
        blocked.append(time.perf_counter() - start)
        first, full = until(lambda: page.picture is not None and page.terrain == terrain and page.scale == 1
                            and page._job is None and shown and shown[-1][1] == terrain and shown[-1][2] == 1,
                            start=start, mark=mark)
        firsts.append(first)
        fulls.append(full)
    row("switch field: Tk blocked by the click", blocked)
    row("switch field: new board on screen", firsts)
    row("switch field: full quality on screen", fulls)
    # Once seen, each field again.
    again = []
    for terrain in ("forest", "normal"):
        page.field.set(terrain)
        start = time.perf_counter()
        page.choose_field()
        until(lambda: page.terrain == terrain and page.scale == 1 and page._job is None
              and shown[-1][1] == terrain and shown[-1][2] == 1)
        again.append(time.perf_counter() - start)
    row("switch field: back to one seen", again)
    # Left alone a while, the page draws the other fields ahead.
    start = time.perf_counter()
    while time.perf_counter() - start < 6 * slow:
        app.update()
        time.sleep(0.005)
        if all(page.view_key(t) + (page.canvas_size(),) in page.pictures for t in ba.TERRAINS
               if hasattr(page, "view_key")):
            break
    ahead = []
    for terrain in ("mountain", "yami", "sogen"):
        page.field.set(terrain)
        start = time.perf_counter()
        page.choose_field()
        until(lambda: page.terrain == terrain and page.scale == 1 and page._job is None
              and shown[-1][1] == terrain and shown[-1][2] == 1)
        ahead.append(time.perf_counter() - start)
    row("switch field after a pause (drawn ahead)", ahead)
    # A middle drag: press, 20 motions each drawn, release.
    width, height = page.canvas_size()
    event = SimpleNamespace(x=width // 2, y=height // 2, state=0)
    page.press(event)
    frames = []
    for i in range(1, 21):
        event = SimpleNamespace(x=width // 2 + 9 * i, y=height // 2 + 3 * i, state=0)
        start = time.perf_counter()
        page.motion(event)
        app.update()
        frames.append(time.perf_counter() - start)
    row("orbit drag: a frame", frames)
    print("drag scale", page.scale)
    start = time.perf_counter()
    page.release(event)
    until(lambda: page.scale == 1 and page._job is None and getattr(page, "_work", None) is None
          and shown[-1][2] == 1)
    row("orbit release: the full render", [time.perf_counter() - start])
    clicks = []
    for key in ("wall_middle", "your_back", "floor", "trim"):
        start = time.perf_counter()
        page.select(key)
        app.update()
        clicks.append(time.perf_counter() - start)
    row("choose a part (outline + form)", clicks)
    picks = []
    for _ in range(5):
        start = time.perf_counter()
        page.clicked(SimpleNamespace(x=width // 2, y=height // 2 + 40))
        app.update()
        picks.append(time.perf_counter() - start)
    row("click the board (pick)", picks)
    page.select("floor")
    start = time.perf_counter()
    page.set_tint(0x80A0FF)
    row("tint the floor: Tk blocked", [time.perf_counter() - start])
    until(lambda: page.scale == 1 and page._job is None and getattr(page, "_work", None) is None and shown[-1][2] == 1)
    row("tint the floor: full quality on screen", [time.perf_counter() - start])
    start = time.perf_counter()
    page.reset_camera()
    row("Game's view: Tk blocked", [time.perf_counter() - start])
    until(lambda: page.scale == 1 and page._job is None and getattr(page, "_work", None) is None and shown[-1][2] == 1)
    row("Game's view: full quality on screen", [time.perf_counter() - start])
    caches()
    start = time.perf_counter()
    tab.page_name.set("duel")
    tab.show_page()
    app.update()
    row("the Duel page (board backdrop, cold)", [time.perf_counter() - start])
    start = time.perf_counter()
    app.notebook.select(app.map)
    app.update()
    app.map.draw()
    app.update()
    row("the Map tab, drawn", [time.perf_counter() - start])
    app.dirty = False
    app.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game", type=Path, default=ROOT / "game")
    parser.add_argument("--no-gui", action="store_true")
    parser.add_argument("--slow", type=int, default=1)
    args = parser.parse_args()
    if not (args.game / "DATA" / "WA_MRG.MRG").is_file():
        sys.exit(f"no game files in {args.game} (--game)")
    if args.slow == 1:
        renders(args.game)
    if not args.no_gui:
        gui(args.game, args.slow)


if __name__ == "__main__":
    main()
