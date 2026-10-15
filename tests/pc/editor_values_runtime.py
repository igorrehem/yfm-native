#!/usr/bin/env python3
"""The FM Editor's Values tab, in the game (built game and user-supplied disc).

Makes a mod through the Values tab as a modder would (each value typed into
its field, one put back with its ↺), exports it as File > Export does, and
plays it through the control channel (tools/pc/yfm_control.py), once with the
mod and once without, so every value is seen to move from the disc's number
to the mod's and the game without the mod to keep the disc's:

  - a duel against Simon Muran, whose deck a fixture mod fixes to Battle Ox
    (1700) and Judge Man (2200): both sides' starting LP; Crush Card
    (destroys from 2000: the Battle Ox stays); Spellbinding Circle and
    Shadow Spell (700 and 1200 off each monster, and the numbers they show);
    Swords of Revealing Light (5 turns: the counter, and the card bar);
    then attacks, turn after turn, to the win and the results: the rank
    score from the mod's start, the starchip prize for the letter (a
    picture each) and the balance it adds to;
  - an Exodia win and a win by the CPU's empty deck: what each adds to the
    rank score;
  - Build Deck: the copies of a card it lets in, and the count turning red;
  - a new game: the starchips the save starts with, on the Password screen.

The CPU's fixed deck is the only mod not made by the editor. Pictures and
logs stay in tmp/pc/editor-values (or --out).

    xvfb-run -a python3 tests/pc/editor_values_runtime.py [--executable PATH] [--out DIR]
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/pc"))
from yfm_control import ControlError, DUEL_PHASES, MODE, Game  # noqa: E402

OUT = ROOT / "tmp/pc/editor-values"
EXECUTABLE = ROOT / "tmp/pc/game32/memories-pc"
MOD, FIXTURE = "values-test", "values-fixture"
# What the editor types into the Values tab.
VALUES = {"life_points.start": 12000, "life_points.opponent": 3000, "deck_copies": 5, "swords_turns": 5,
          "crush_card": 2000, "spellbinding_circle": 700, "shadow_spell": 1200, "rank_score.start": 60,
          "rank_score.exodia": 20, "rank_score.deck_out": -10, "starchip_prize.S": 8, "starchip_prize.A": 7,
          "starchip_prize.B": 6, "starchip_prize.C": 5, "starchip_prize.D": 4, "new_game_starchips": 4321}
# The disc's, which a game without the mod must keep.
RETAIL = {"life_points.start": 8000, "life_points.opponent": 8000, "deck_copies": 3, "swords_turns": 3,
          "crush_card": 1500, "spellbinding_circle": 500, "shadow_spell": 1000, "rank_score.start": 50,
          "rank_score.exodia": 40, "rank_score.deck_out": -40, "starchip_prize.S": 5, "starchip_prize.A": 4,
          "starchip_prize.B": 3, "starchip_prize.C": 2, "starchip_prize.D": 1, "new_game_starchips": 0}
LETTERS = "DCBAS"   # rank tier 0 to 4
BEWD, ELF, SWORDS, CRUSH, SPELLBINDING, SHADOW = 1, 2, 348, 661, 349, 669
BATTLE_OX, JUDGE_MAN = 26, 33
EXODIA = [17, 18, 19, 20, 21]
SIDE = 0x20                       # duel_side_state.h: DuelSideState
SWORDS_TURNS = 0x19               # its swords_turns_remaining
DECK_CURSOR = 0x18                # its deck_draw_cursor
STAT_MODIFIER = 0x12              # duel_card.h: DuelCardRecord.stat_modifier
# duel_result_display.h: DuelResultDisplayState (at gDuel_awRitualData).
SCORES, TIER, TEC, PRIZE = 0x2C, 0x38, 0x39, 0x3A
# Duel_CalcRankScore's statistics rows (text_staging.h rank_rows, by side)
# and the rule each is scored by (duel_rank.h).
RANK_ROWS = {0: 6, 1: 7, 4: 1, 7: 2, 9: 3, 10: 8, 11: 9, 13: 4, 14: 5, 15: 0}


def make_mod(game: Path, out: Path, shots: Path) -> dict:
    """The mod, typed into the Values tab; its "limits" as exported."""
    from fm_editor import validate
    from fm_editor.app import App
    answers = [mock.patch("tkinter.messagebox." + n, return_value=True) for n in ("askyesno", "askokcancel")]
    for patch in answers:
        patch.start()
    app = App(ask=False, autostart=False)
    app.geometry("1280x800")
    app.update()
    app.start(str(game), None, False)
    app.update()
    app.info.vars["id"].set(MOD)
    app.info.vars["name"].set("Values test")
    assert app.info.commit()
    tab = app.values
    app.notebook.select(tab.page)
    app.update()
    for key, value in VALUES.items():
        tab.vars[key].set(str(value))
        assert tab.commit(), key
    # One more, and ↺ to take it back: the game's own again.
    tab.vars["stats"].set("12000")
    assert tab.commit()
    assert str(tab.reverts["stats"].cget("state")) == "normal"
    tab.revert("stats")
    assert "stats" not in app.project.other["limits"]
    app.update()
    assert not [issue for issue in validate.validate(app.project) if issue.area == "Values"]
    with mock.patch("tkinter.filedialog.askdirectory", return_value=str(out / "mods")):
        assert app.save(ask=True, export=True)
    app.dirty = False
    app.destroy()
    for patch in answers:
        patch.stop()
    limits = json.loads((out / "mods" / MOD / "mod.json").read_text(encoding="utf-8"))["limits"]
    fixture = out / "mods" / FIXTURE
    fixture.mkdir(parents=True, exist_ok=True)
    (fixture / "mod.json").write_text(json.dumps({
        "id": FIXTURE, "name": "Values test: the CPU's deck",
        "decks": {"Simon Muran": {"fixed": True, "Battle Ox": 20, "Judge Man": 20}}}), encoding="utf-8")
    return limits


class Run:
    """The game with the mod ("mod") or without it ("retail"); `want` is
    what each value must be in it."""

    def __init__(self, executable: Path, out: Path, shots: Path, which: str):
        self.executable, self.out, self.shots, self.which = executable, out, shots, which
        self.want = VALUES if which == "mod" else RETAIL
        self.settings = {"mod.3d-monsters": 0, "mod.hand-camera": 0, "mod.ai-hard-mode": 0,
                         f"mod.{FIXTURE}": 1, f"mod.{MOD}": 1 if which == "mod" else 0}
        self.done = []

    def game(self, name: str) -> Game:
        return Game(executable=self.executable, out=self.out / f"{self.which}-{name}", mods_dir=self.out / "mods",
                    settings=self.settings, env={"MEMORIES_TRACE": "mods"})

    def shot(self, game: Game, name: str) -> Path:
        path = game.shot(f"{name}.png")
        self.shots.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, self.shots / f"{self.which}-{name}.png")
        return path

    def ok(self, text: str) -> None:
        self.done.append(text)
        print(f"  {self.which}: {text}", flush=True)

    # --- the duel ---------------------------------------------------------

    def duel(self) -> None:
        want = self.want
        deck = [BEWD, SWORDS, CRUSH, SPELLBINDING, SHADOW] + [BEWD] * 3 + [ELF] * 32
        with self.game("duel") as g:
            g.goto("duel", opponent=1, deck=deck)
            # The CPU plays its strongest card each turn: a Judge Man, then
            # Battle Ox after Battle Ox.
            g.duel_ready(before_deal=lambda g: (g.arrange_deck(0, deck[:8]),
                                                g.arrange_deck(1, [JUDGE_MAN] + [BATTLE_OX] * 7)))
            sides = g.duel()
            lp = (want["life_points.start"], want["life_points.opponent"])
            assert (sides[0]["lp"], sides[1]["lp"]) == lp, (sides[0]["lp"], sides[1]["lp"])
            assert (sides[0]["max_lp"], sides[1]["max_lp"]) == lp
            self.shot(g, "duel-start")
            self.ok(f"starting LP {lp[0]} and the CPU's {lp[1]}")
            self.play(g, BEWD, face_up=True)
            g.end_turn()
            self.play(g, BEWD, face_up=True)
            g.end_turn()
            before = self.monsters(g)
            assert sorted(m[0] for m in before if m) == [BATTLE_OX, JUDGE_MAN], before
            self.play(g, CRUSH)
            after = [m[0] for m in self.monsters(g) if m]
            survivors = [card for card in (BATTLE_OX, JUDGE_MAN)
                         if {BATTLE_OX: 1700, JUDGE_MAN: 2200}[card] < want["crush_card"]]
            assert after == survivors, (after, survivors)
            self.shot(g, "crush-card")
            self.ok(f"Crush Card destroys from {want['crush_card']} ATK: {after or 'nothing'} left")
            g.end_turn()
            for card, key in ((SPELLBINDING, "spellbinding_circle"), (SHADOW, "shadow_spell")):
                before = self.monsters(g)
                self.film(g, card, key)
                after = self.monsters(g)
                for old, new in zip(before, after):
                    if old:
                        assert new and new[1] == max(old[1] - want[key], -32768), (key, before, after)
                assert any(before), before
                self.ok(f"{key}: {want[key]} off each of the CPU's {sum(1 for m in before if m)} monsters")
                g.end_turn()
            self.play(g, SWORDS)
            counter = g.u8(g.address("D_800E9FF0") + SIDE + SWORDS_TURNS)
            assert counter == want["swords_turns"] + 1, counter
            g.step(30)
            # The card bar over the CPU's monsters: the field cursor's row
            # (FIELD_CURSOR + 1) up to theirs.
            g.press_until(lambda g: g.u8(0x800E9F58) == 1, "up", every=30, timeout=600, what="their row")
            g.step(30)
            self.shot(g, "swords-card-bar")
            self.ok(f"Swords of Revealing Light: counter {counter}, {want['swords_turns']} turns on the card bar")
            g.press_until(lambda g: g.u8(0x800E9F58) == 2, "down", every=30, timeout=600, what="our row")
            # To the end: every monster attacks each turn, and a Blue-eyes
            # is played while there is one in the hand.
            starchips = g.u32("gLibrary_dwStarchips")
            turns, swords = 0, []
            while not g.duel_over():
                self.attack_all(g)
                if g.duel_over():
                    break
                g.end_turn()
                turns += 1
                swords.append(g.u8(g.address("D_800E9FF0") + SIDE + SWORDS_TURNS))
                assert turns < 20, "no end in sight"
                if not g.duel_over():
                    self.play_any(g)
            # The counter: one a CPU turn, from the value + 1 down to 0.
            expected = [max(want["swords_turns"] - i, 0) for i in range(len(swords))]
            assert swords == expected, (swords, expected)
            self.ok(f"won after {turns + 6} turns (the Swords' counter by turn: {swords})")
            self.results(g, "duel")
            self.leave_results(g, starchips)

    def play(self, g: Game, card: int, face_up: bool = False) -> None:
        g.play_card(self.slot(g, card), face_up=face_up)

    def play_any(self, g: Game) -> None:
        hand = g.duel()[0]["hand"]
        slot = next((i for i, c in enumerate(hand) if c and c["id"] == BEWD), None)
        if slot is None:
            slot = next(i for i, c in enumerate(hand) if c)
        g.play_card(slot, face_up=hand[slot]["id"] == BEWD)

    def attack_all(self, g: Game) -> None:
        for column in range(5):
            if g.duel_over():
                return
            field = g.field()
            if not field[2][column]:
                continue
            targets = [i for i, c in enumerate(field[1]) if c]
            try:
                g.attack(column, targets[0] if targets else None)
            except ControlError:
                pass        # a monster played this turn, or one the cursor skips: it waits a turn

    @staticmethod
    def slot(g: Game, card: int) -> int:
        return next(i for i, c in enumerate(g.duel()[0]["hand"]) if c and c["id"] == card)

    @staticmethod
    def monsters(g: Game) -> list:
        """The CPU's monster zones: (card, stat_modifier) or None."""
        records = g.peek("D_801A7AD8", 30 * 0x1C)
        out = []
        for index, monster in zip(range(20, 25), g.duel()[1]["monsters"]):
            out.append((monster["id"], struct.unpack_from("<h", records, index * 0x1C + STAT_MODIFIER)[0])
                       if monster else None)
        return out

    def film(self, g: Game, card: int, key: str) -> None:
        """A magic card from the hand, its number filmed as it shows."""
        g.wait_turn(("hand",))
        g._hand_to(self.slot(g, card))
        g.press("cross", hold=4, after=30)
        g.press_until(lambda g: g.phase() != DUEL_PHASES["hand"], "cross", every=40, timeout=1200)
        g.press_until(lambda g: g.phase() != DUEL_PHASES["placement"], "cross", every=40, timeout=1200)
        for frame in range(0, 480, 8):
            g.step(8)
            if 128 <= frame <= 176:       # the number over the monsters
                self.shot(g, f"{key}-{frame:03d}")
        g._settle()

    def results(self, g: Game, name: str) -> None:
        """The rank score and the prize on the results screen, as worked
        out here from the duel's statistics and the rank table."""
        want = self.want
        g.wait_until(lambda g: g.phase() == DUEL_PHASES["rewards"], 6000, what="the rewards")
        g.step(120)
        data = g.peek("gDuel_awRitualData", 0x40)
        winner = g.u8("gDuel_bWinnerSide")
        assert winner == 0, winner
        score = struct.unpack_from("<i", data, SCORES)[0]
        rows = struct.unpack_from("<32i", g.peek("D_801D5608", 32 * 4))
        table = struct.unpack("<100h", g.peek("gDuel_awRankScoreChange", 200))

        def change(rule, value):
            k = rule * 5
            while value >= table[2 * k]:
                k += 1
            return table[2 * k + 1]
        tag = struct.unpack_from("<b", g.peek("D_800E9FF0", 1))[0]
        added = {40: want["rank_score.exodia"], -40: want["rank_score.deck_out"]}.get(tag, tag)
        expected = want["rank_score.start"] + added + sum(change(rule, rows[2 * row]) for row, rule in
                                                           RANK_ROWS.items())
        assert score == expected, (score, expected, tag)
        tec, tier = data[TEC], data[TIER]
        graded = score if score >= 50 else 99 - max(score, 0)
        assert tec == (score < 50) and tier == (min(graded, 99) - 50) // 10, (score, tec, tier)
        prize = want[f"starchip_prize.{LETTERS[tier]}"]
        shown = struct.unpack_from("<H", data, PRIZE)[0]   # a halfword on the PC (duel_result_display.h)
        assert shown == prize, (shown, prize)
        self.shot(g, f"{name}-results")
        self.ok(f"{name}: rank score {score} (start {want['rank_score.start']}, end tag {tag} adds {added}), "
                f"{'TEC' if tec else 'POW'} {LETTERS[tier]}, {prize} starchips shown")
        self.prize = prize

    def leave_results(self, g: Game, starchips: int) -> None:
        for page in (1, 2):
            g.press("right", hold=4, after=60)
            self.shot(g, f"duel-results-page{page}")
        g.press_until(lambda g: g.mode() != MODE["duel"], "cross", every=60, timeout=3000, what="the duel's end")
        g.step(120)
        balance = g.u32("gLibrary_dwStarchips")
        assert balance == starchips + self.prize, (starchips, balance, self.prize)
        self.ok(f"starchips {starchips} -> {balance}")

    # --- the ends of a duel ----------------------------------------------

    def ends(self, repeats: int = 1) -> None:
        for iteration in range(repeats):
            self.end_pair(iteration if repeats > 1 else None)

    def end_pair(self, iteration: int | None) -> None:
        suffix = "" if iteration is None else f"-{iteration}"

        def arrange(g):
            g.arrange_deck(0, EXODIA)
            if iteration is not None:
                # Vary the ray choreography reproducibly across fresh games.
                g.poke("gRand_dwSeed", struct.pack("<I", iteration + 1))

        with self.game(f"ends{suffix}") as g:
            g.goto("duel", opponent=1, deck=EXODIA + [ELF] * 35)
            g.duel_ready(before_deal=arrange)
            self.results(g, f"exodia{suffix}")
            g.goto("duel", opponent=1, deck=[ELF] * 40)
            g.duel_ready()
            g.play_card(0)
            # The CPU's next draw is past its forty: it loses by its empty deck.
            g.poke(g.address("D_800E9FF0") + SIDE + DECK_CURSOR, bytes([40]))
            g.press_until(lambda g: g.turn() != 0 or g.duel_over(), "start", every=60, timeout=1200)
            self.results(g, f"deck-out{suffix}")

    # --- Build Deck ------------------------------------------------------

    def build_deck(self) -> None:
        copies = self.want["deck_copies"]
        with self.game("build-deck") as g:
            g.goto("debug")
            g.step(30)
            # 30 cards in the deck, ten slots free; nine Blue-eyes and ten
            # other cards, one each, in the chest.
            g.poke("gDuel_awPlayerDeck", struct.pack("<40H", *(list(range(100, 130)) + [0] * 10)))
            chest = bytearray(722)
            chest[BEWD - 1] = 9
            for card in range(3, 13):
                chest[card - 1] = 1
            g.poke("gLibrary_abCardChest", bytes(chest))
            g.goto("build_deck")
            g.step(300)
            for _ in range(9):            # Cross on the Blue-eyes, as many times as the chest has it
                g.press("cross", hold=4, after=30)
            self.shot(g, "build-deck")
            for _ in range(10):           # the deck filled with the others, to leave with forty
                g.press("down", hold=4, after=20)
                g.press("cross", hold=4, after=30)
            g.press("circle", hold=4, after=120)     # back to the debug menu: the deck is saved
            g.step(120)
            deck = g.state()["deck"]
            assert deck.count(BEWD) == copies and 0 not in deck, sorted(deck)
            self.ok(f"Build Deck lets {copies} Blue-eyes in (of 9 tries); the deck saved with them")

    # --- a new game ------------------------------------------------------

    def new_game(self) -> None:
        with self.game("new-game") as g:
            g.wait_until(lambda g: g.resident("main_menu"), 3000, what="the title")
            g.press_until(lambda g: g.resident("password"), ["start", "cross"], every=40, what="the name entry")
            g.press_until(lambda g: g.player_name(), "cross", every=20, what="a letter of the name")
            g.press("start")
            g.press_until(lambda g: g.mode() == MODE["campaign"], "cross", every=40, what="the story")
            starchips = g.u32("gLibrary_dwStarchips")
            assert starchips == self.want["new_game_starchips"], starchips
            g.goto("password")
            g.step(240)
            self.shot(g, "new-game-password-screen")
            self.ok(f"a new game starts with {starchips} starchips")

    def said(self) -> str:
        """Every game's log: no note against the mod, its values read."""
        text = "".join(path.read_text(errors="replace") for path in self.out.glob(f"{self.which}-*/game.log"))
        notes = [line for line in text.splitlines() if f"mod {MOD}:" in line or f"mod {FIXTURE}:" in line]
        assert not notes, "\n".join(notes)
        return text


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--executable", type=Path, default=EXECUTABLE)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--shots", type=Path, help="where the pictures are copied (default OUT/shots)")
    parser.add_argument("--parts", default="duel,ends,build_deck,new_game", help="which checks (comma-separated)")
    parser.add_argument("--end-repeats", type=int, default=1,
                        help="repeat Exodia/deck-out in fresh games with varied RNG seeds")
    arguments = parser.parse_args()
    if arguments.end_repeats < 1:
        parser.error("--end-repeats must be at least 1")
    out = arguments.out
    shots = arguments.shots or out / "shots"
    shutil.rmtree(out, ignore_errors=True)
    (out / "mods").mkdir(parents=True)
    game = Path(os.environ.get("MEMORIES_DISC_DIR", ROOT / "game"))
    limits = make_mod(game, out, shots)
    print("the Values tab wrote:", json.dumps(limits))
    for which in ("mod", "retail"):
        run = Run(arguments.executable, out, shots, which)
        parts = arguments.parts.split(",")
        for part in parts:
            if part == "ends":
                run.ends(arguments.end_repeats)
            else:
                getattr(run, part)()
        said = run.said()
        if which == "mod":
            for key in VALUES:
                if not key.startswith("life_points"):
                    assert f"tables: value {key} {VALUES[key]}" in said, key
        else:
            assert "tables: value" not in said
    print(f"values: every value the game's own without the mod and the mod's with it (pictures in {shots})")


if __name__ == "__main__":
    main()
