"""The Cards tab's Monster effects list and the dialog that makes or
changes one (monster_effects.py has what the game takes)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import card_icons, manifest, monster_effects as fx
from .icon_choice import IconChoice
from .gamedata import ATTRIBUTE_NAMES, TYPE_MAGIC, TYPE_NAMES
from .widgets import FormDialog, px, scrolled_tree

ANY = "Any"


class EffectsBox(ttk.LabelFrame):
    """A monster's effects: a row each, in the order they resolve, and the
    buttons that change them. Each change is stored at once (on_change)."""

    def __init__(self, master, app, on_change):
        super().__init__(master, text="Monster effects", padding=6)
        self.app, self.on_change = app, on_change
        self.cid = None
        self.effects = []
        frame, self.tree = scrolled_tree(self, [("when", "When"), ("what", "Does")], [110, 250], 4)
        frame.grid(row=0, column=0, columnspan=6, sticky="we")
        self.list_frame = frame         # shown once there is an effect: an empty list took a quarter of the form
        self.columnconfigure(5, weight=1)
        self.tree.bind("<Double-1>", lambda e: self.edit())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_buttons())
        self.buttons = {}
        for column, (key, text, command) in enumerate((("add", "Add...", self.add), ("edit", "Edit...", self.edit),
                                                        ("remove", "Remove", self.remove),
                                                        ("up", "Up", lambda: self.move(-1)),
                                                        ("down", "Down", lambda: self.move(1)))):
            self.buttons[key] = ttk.Button(self, text=text, command=command, width=8 if column < 3 else 5)
            self.buttons[key].grid(row=1, column=column, sticky="w", pady=(4, 0), padx=(0, 4))
        self.note = ttk.Label(self, style="Hint.TLabel", wraplength=px(self, 380), justify="left")
        self.note.grid(row=2, column=0, columnspan=6, sticky="w", pady=(4, 0))
        # A disc card with no effects: "monster_effects": [] takes away any
        # an earlier mod gives it (cards.c), left out leaves them.
        self.none = tk.BooleanVar(self)
        self.none_box = ttk.Checkbutton(self, text="Force no effects", variable=self.none,
                                        command=self.store)
        self.none_box.grid(row=3, column=0, columnspan=6, sticky="w", pady=(4, 0))

    @property
    def project(self):
        return self.app.project

    def show(self, cid):
        """The card's list (an added card's base's, until it has its own)."""
        self.cid = cid
        if cid is None or self.project is None or cid not in self.project.cards:
            self.effects = []
        else:
            effects, _ = self.project.monster_effects_of(cid)
            # An entry that is not an object stays as written (the game leaves it out).
            self.effects = [dict(e) if isinstance(e, dict) else e for e in effects]
        retail = cid is not None and self.project is not None and cid in self.project.cards and \
            cid not in self.project.added
        extra = self.project.card_extra.get(cid, {}) if retail else {}
        self.none.set(retail and extra.get("monster_effects") == [])
        if retail and not self.effects:
            self.none_box.grid()
        else:
            self.none_box.grid_remove()
        self.fill()
        # No effect: Add... and a line, not an empty list and greyed buttons.
        if self.effects:
            self.list_frame.grid()
            for key in ("edit", "remove", "up", "down"):
                self.buttons[key].grid()
        else:
            self.list_frame.grid_remove()
            for key in ("edit", "remove", "up", "down"):
                self.buttons[key].grid_remove()
        if not self.effects and cid is not None:
            self.note.configure(text="No effects")
        else:
            # Only what is wrong with the list; nothing when it is fine.
            problems = fx.problems(self.effects, self.project.resolve if self.project else None,
                                   self.attribute_choice if self.project else None)
            self.note.configure(text="\n".join(problems))
        if self.note.cget("text"):
            self.note.grid()
        else:
            self.note.grid_remove()

    def label(self, cid):
        card = self.project.cards.get(cid) if self.project else None
        return card.name if card else f"#{cid}"

    def attribute_choice(self, value):
        return manifest._attribute_choice(value, self.project.other.get("attributes"))

    def fill(self):
        self.tree.delete(*self.tree.get_children())
        for n, effect in enumerate(self.effects):
            normalized = fx.normalize(effect, self.project.resolve, self.attribute_choice)
            if normalized is None:
                when = effect.get("when", "?") if isinstance(effect, dict) else "?"
                self.tree.insert("", "end", iid=str(n), values=(when, "(not one the game takes) " +
                                                                fx.describe_raw(effect)))
                continue
            self.tree.insert("", "end", iid=str(n), values=(fx.when_label(fx._name(fx.WHEN, effect.get("when"))),
                                                            fx.describe(normalized, self.label)))
        self.show_buttons()

    def selected(self):
        chosen = self.tree.selection()
        return int(chosen[0]) if chosen else None

    def show_buttons(self):
        n = self.selected()
        enabled = self.cid is not None
        self.buttons["add"].state(["!disabled"] if enabled and len(self.effects) < fx.MAX_EFFECTS else ["disabled"])
        for key in ("edit", "remove"):
            self.buttons[key].state(["!disabled"] if n is not None else ["disabled"])
        self.buttons["up"].state(["!disabled"] if n else ["disabled"])
        self.buttons["down"].state(["!disabled"] if n is not None and n < len(self.effects) - 1 else ["disabled"])

    def store(self, select=None):
        if self.cid is None:
            return
        self.project.set_monster_effects(self.cid, self.effects, keep_empty=self.none.get())
        self.on_change(self.cid)
        self.show(self.cid)
        if select is not None and str(select) in self.tree.get_children():
            self.tree.selection_set(str(select))

    def add(self):
        if self.cid is None:
            return
        dialog = EffectDialog(self, self.project, None, self.label, self.app)
        self.wait_window(dialog)
        if dialog.result is not None:
            self.effects.append(dialog.result)
            self.store(len(self.effects) - 1)

    def edit(self):
        n = self.selected()
        if n is None:
            return
        dialog = EffectDialog(self, self.project, self.effects[n], self.label, self.app)
        self.wait_window(dialog)
        if dialog.result is not None:
            self.effects[n] = dialog.result
            self.store(n)

    def remove(self):
        n = self.selected()
        if n is None:
            return
        del self.effects[n]
        # An added card with none left has none: not its base's again.
        self.store(min(n, len(self.effects) - 1) if self.effects else None)

    def move(self, step):
        n = self.selected()
        if n is None or not 0 <= n + step < len(self.effects):
            return
        self.effects[n], self.effects[n + step] = self.effects[n + step], self.effects[n]
        self.store(n + step)


class EffectDialog(FormDialog):
    """One effect: when, what, and what that needs. result is the entry
    as the game reads it, or None when cancelled."""

    def __init__(self, master, project, effect, label, app=None):
        """app: the window, whose game files give the lists' icons (none without)."""
        self.project, self.label, self.app = project, label, app
        self.result = None
        effect = fx.normalize(effect, project.resolve, self.attribute_choice) if effect else None
        self.start = effect or {"when": "summon", "do": "boost", "target": "self", "attack": 500}
        super().__init__(master, "Monster effect" if effect is None else "Change the monster effect", self.build,
                         self.read)

    def magic_label(self, cid):
        return f"{cid} {self.label(cid)}"

    def attribute_choice(self, value):
        return manifest._attribute_choice(value, self.project.other.get("attributes"))

    def custom_attribute_labels(self):
        names, declared = manifest._attribute_registry(self.project.other.get("attributes"))
        return {(f"{names[ident]} ({ident})" if names[ident] == ANY else names[ident]): ident
                for ident in sorted(declared)}

    def attribute_names(self):
        names, declared = manifest._attribute_registry(self.project.other.get("attributes"))
        labels = self.custom_attribute_labels()
        retail = [next((label for label, ident in labels.items() if ident == ident_), names[ident_])
                  for ident_ in range(len(ATTRIBUTE_NAMES))]
        return [ANY] + retail + [label for label, ident in labels.items() if ident >= len(ATTRIBUTE_NAMES)]

    def attribute_label(self, value):
        names, declared = manifest._attribute_registry(self.project.other.get("attributes"))
        if type(value) is int and value in declared:
            return next(label for label, ident in self.custom_attribute_labels().items() if ident == value)
        return names[value] if type(value) is int and 0 <= value < len(ATTRIBUTE_NAMES) else value

    def attribute_value(self, label):
        return self.custom_attribute_labels().get(label, label)

    def build(self, dialog, body):
        e = self.start
        self.vars = {k: tk.StringVar(dialog) for k in ("when", "do", "card", "target", "type", "attribute", "attack",
                                                 "defense", "amount", "each", "each_type", "each_attribute")}
        self.rows = {}
        row = 0

        def line(key, label, widget):
            nonlocal row
            caption = ttk.Label(body, text=label)
            caption.grid(row=row, column=0, sticky="w", pady=2)
            widget.grid(row=row, column=1, sticky="we", pady=2)
            self.rows[key] = (caption, widget)
            row += 1
            return widget

        line("when", "When", ttk.Combobox(body, textvariable=self.vars["when"], values=list(fx.WHEN_LABELS),
                                          state="readonly", width=30))
        self.when_hint = ttk.Label(body, style="Hint.TLabel", wraplength=px(body, 300), justify="left")
        self.when_hint.grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 4))
        row += 1
        self.do_box = line("do", "Does", ttk.Combobox(body, textvariable=self.vars["do"], state="readonly", width=30))
        line("card", "Magic card", self.choice(body, "card", [self.magic_label(c) for c in fx.MAGIC], lambda v: 0x14))
        self.target_box = line("target", "Whose", ttk.Combobox(body, textvariable=self.vars["target"],
                                                               state="readonly", width=30))
        line("type", "Only type", self.choice(body, "type", [ANY] + TYPE_NAMES[:TYPE_MAGIC],
                                              lambda v: TYPE_NAMES.index(v) if v in TYPE_NAMES else None))
        line("attribute", "Only attribute", self.choice(body, "attribute", self.attribute_names(), self.attribute_icon))
        pictures = card_icons.photos(self.app, body, 2) if self.app is not None else {}
        for key, label in (("attack", "ATK"), ("defense", "DEF")):
            line(key, label, ttk.Spinbox(body, textvariable=self.vars[key], from_=-fx.BOOST_MAX, to=fx.BOOST_MAX,
                                         increment=100, width=10))
            if pictures.get(key):       # the sword and the shield, as the Cards tab's
                self.rows[key][0].configure(image=pictures[key], compound="left")
        line("amount", "LP", ttk.Spinbox(body, textvariable=self.vars["amount"], from_=1, to=fx.AMOUNT_MAX,
                                         increment=100, width=10))
        # "for_each": the number above made once per face-up monster counted.
        line("each", "For each", ttk.Combobox(body, textvariable=self.vars["each"], state="readonly", width=30,
                                              values=[fx.NO_EACH] + list(fx.EACH_LABELS)))
        line("each_type", "Counting type", self.choice(body, "each_type", [ANY] + TYPE_NAMES[:TYPE_MAGIC],
                                                       lambda v: TYPE_NAMES.index(v) if v in TYPE_NAMES else None))
        line("each_attribute", "Counting attribute", self.choice(body, "each_attribute", self.attribute_names(),
                                                                 self.attribute_icon))
        self.vars["when"].set(fx.when_label(e["when"]))
        self.vars["do"].set(fx.DO_LABELS[fx.DO.index(e["do"])])
        self.vars["card"].set(self.magic_label(e.get("card", 337)))
        target = e.get("target", fx.default_target(e["when"], e["do"]))
        self.vars["target"].set(fx.TARGET_LABELS[fx.TARGET.index(target)])
        self.vars["type"].set(e.get("type", ANY))
        self.vars["attribute"].set(self.attribute_label(e.get("attribute", ANY)))
        self.vars["attack"].set(e.get("attack", 0))
        self.vars["defense"].set(e.get("defense", 0))
        self.vars["amount"].set(e.get("amount", 500))
        each = e.get("for_each")
        self.vars["each"].set(fx.EACH_LABELS[fx.EACH.index(each["whose"])] if each else fx.NO_EACH)
        self.vars["each_type"].set((each or {}).get("type", ANY))
        self.vars["each_attribute"].set(self.attribute_label((each or {}).get("attribute", ANY)))
        for key in ("when", "do", "each"):
            self.vars[key].trace_add("write", lambda *_: self.show_rows())
        self.show_rows()

    def choice(self, body, key, values, icon_of):
        """A list with the game's icons beside its choices (icon_choice.py),
        or a plain one without a window to take them from."""
        if self.app is None:
            return ttk.Combobox(body, textvariable=self.vars[key], state="readonly", width=30, values=values)
        return IconChoice(body, self.app, self.vars[key], values, icon_of, width=30)

    def attribute_icon(self, value):
        ident = self.attribute_choice(value)
        if not 0 <= ident < len(ATTRIBUTE_NAMES):
            return None
        return card_icons.photos(self.app, self).get("attribute", {}).get(ident)

    def chosen(self, key, names, labels):
        text = self.vars[key].get()
        return names[labels.index(text)] if text in labels else None

    def show_rows(self):
        when = self.chosen("when", fx.WHEN, fx.WHEN_LABELS) or "summon"
        self.when_hint.configure(text=fx.WHEN_HINTS[fx.WHEN.index(when)])
        actions = fx.actions(when)
        self.do_box.configure(values=[fx.DO_LABELS[fx.DO.index(a)] for a in actions])
        do = self.chosen("do", fx.DO, fx.DO_LABELS)
        if do not in actions:
            do = actions[0]
            self.vars["do"].set(fx.DO_LABELS[fx.DO.index(do)])
            return      # the trace calls again
        targets = fx.targets(when, do if do in fx.FILTERED else "boost")
        self.target_box.configure(values=[fx.TARGET_LABELS[fx.TARGET.index(t)] for t in targets])
        if self.chosen("target", fx.TARGET, fx.TARGET_LABELS) not in targets:
            self.vars["target"].set(fx.TARGET_LABELS[fx.TARGET.index(targets[0])])
        shown = {"when", "do"} | {"magic": {"card"}, "boost": {"target", "type", "attribute", "attack", "defense"},
                                  "heal": {"amount"}, "damage": {"amount"},
                                  "destroy": {"target", "type", "attribute"}}[do]
        if do in fx.EACH_DO:
            shown.add("each")
            if self.vars["each"].get() in fx.EACH_LABELS:
                shown |= {"each_type", "each_attribute"}
        for key, widgets in self.rows.items():
            for widget in widgets:
                widget.grid() if key in shown else widget.grid_remove()

    def read(self, dialog):
        when = self.chosen("when", fx.WHEN, fx.WHEN_LABELS)
        do = self.chosen("do", fx.DO, fx.DO_LABELS)
        if not when or not do:
            return "Choose when and what."
        effect = {"when": when, "do": do}
        if do == "magic":
            text = self.vars["card"].get()
            effect["card"] = int(text.split(" ", 1)[0]) if text[:1].isdigit() else 0
        elif do in fx.FILTERED:
            effect["target"] = self.chosen("target", fx.TARGET, fx.TARGET_LABELS)
            for key in ("attack", "defense") if do == "boost" else ():
                text = self.vars[key].get().strip() or "0"
                try:
                    value = int(text)
                except ValueError:
                    return "ATK and DEF are whole numbers (negative takes away)."
                if abs(value) > fx.BOOST_MAX:
                    return f"ATK and DEF are -{fx.BOOST_MAX} to {fx.BOOST_MAX}."
                if value:
                    effect[key] = value
            if do == "boost" and "attack" not in effect and "defense" not in effect:
                return "A boost needs ATK or DEF."
            for key in ("type", "attribute"):
                if self.vars[key].get() not in ("", ANY):
                    effect[key] = self.attribute_value(self.vars[key].get()) if key == "attribute" else self.vars[key].get()
        else:
            try:
                effect["amount"] = int(self.vars["amount"].get().strip())
            except ValueError:
                return "LP is a whole number."
            if not 0 < effect["amount"] <= fx.AMOUNT_MAX:
                return f"LP is 1 to {fx.AMOUNT_MAX}."
        whose = self.chosen("each", fx.EACH, fx.EACH_LABELS)
        if whose and do in fx.EACH_DO:
            effect["for_each"] = {"whose": whose}
            for key in ("type", "attribute"):
                if self.vars["each_" + key].get() not in ("", ANY):
                    value = self.vars["each_" + key].get()
                    effect["for_each"][key] = self.attribute_value(value) if key == "attribute" else value
        effect = fx.normalize(effect, self.project.resolve, self.attribute_choice)
        if effect is None:
            return "The game cannot do that."
        self.result = effect
        return None
