"""Every button of every tab, pressed: with a row of each list picked, the
question dialogs answered yes, the file dialogs cancelled and the editor's
own dialogs closed, no button raises. The other tests check what each one
does; this one makes sure none is left that breaks when pressed.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import unittest
from unittest import mock

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:     # a Python built without Tk
    tk = None

from fm_editor.tests.test_gui import GuiCase


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class EveryButtonTest(GuiCase):
    def press_all(self, tab, rounds=1):
        app = self.app
        errors = []
        app.report_callback_exception = lambda kind, value, trace: errors.append(
            f"{app.notebook.tab(tab.page, 'text')}: {kind.__name__}: {value}")
        windows = lambda: {w for w in descendants(app) if isinstance(w, tk.Toplevel)}  # noqa: E731
        before = windows()
        for _ in range(rounds):
            for tree in [w for w in descendants(tab) if isinstance(w, ttk.Treeview)]:
                rows = tree.get_children()
                if rows and not tree.selection():
                    tree.selection_set(rows[0])
                    tree.event_generate("<<TreeviewSelect>>")
            app.update()
            presses = []
            for widget in descendants(tab):
                if isinstance(widget, ttk.Button):
                    presses.append((repr(widget.cget("text")), widget.invoke, widget))
                elif isinstance(widget, ttk.Menubutton) and widget.cget("menu"):
                    menu = widget.nametowidget(widget.cget("menu"))
                    for i in range((menu.index("end") or -1) + 1):
                        if menu.type(i) in ("command", "radiobutton", "checkbutton"):
                            presses.append((repr(menu.entrycget(i, "label")), lambda m=menu, i=i: m.invoke(i), widget))
            for name, press, widget in presses:
                if not widget.winfo_exists() or widget.instate(["disabled"]):
                    continue
                try:
                    press()
                    self.pressed += 1
                except Exception as problem:      # noqa: BLE001 -- every one is reported
                    errors.append(f"{name}: {type(problem).__name__}: {problem}")
                app.update()
                # A dialog it opened: OK (or Save) pressed as it stands, then closed.
                for window in windows() - before:
                    if window.winfo_exists():
                        for button in [w for w in descendants(window) if isinstance(w, ttk.Button)
                                       and w.cget("text") in ("OK", "Save", "Apply")]:
                            try:
                                if button.winfo_exists():
                                    button.invoke()
                                    self.dialogs += 1
                            except Exception as problem:      # noqa: BLE001
                                errors.append(f"{name} > {button.cget('text')}: {type(problem).__name__}: {problem}")
                            app.update()
                        if window.winfo_exists():
                            window.destroy()
                app.update()
        return errors

    def test_every_button_of_every_tab(self):
        app = self.app
        app.deiconify()
        app.geometry("1400x900")
        patches = [mock.patch("tkinter.messagebox." + name, return_value=True)
                   for name in ("askyesno", "askokcancel", "askyesnocancel")]
        patches += [mock.patch("tkinter.messagebox." + name, return_value="ok")
                    for name in ("showinfo", "showwarning", "showerror")]
        patches += [mock.patch("tkinter.filedialog." + name, return_value="")
                    for name in ("askopenfilename", "asksaveasfilename", "askdirectory", "askopenfilenames")]
        # A dialog that waits for its answer returns at once (and is closed).
        patches.append(mock.patch.object(tk.Misc, "wait_window", lambda self, window=None: None))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        problems = []
        self.pressed = self.dialogs = 0
        for tab in app.tabs:
            app.notebook.select(tab)
            app.update()
            problems += self.press_all(tab, rounds=2)
        self.assertEqual(problems, [])
        self.assertGreater(self.pressed, 150)        # every tab's, twice
        self.assertGreater(self.dialogs, 5)
        # And the window is still whole: every tab fills again.
        for tab in app.tabs:
            app.notebook.select(tab)
            app.update()


if __name__ == "__main__":
    unittest.main()
