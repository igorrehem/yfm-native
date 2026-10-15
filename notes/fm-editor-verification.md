# FM Editor verification — 2026-10-10

**Result: all 14 editor tabs were exercised; the two gameplay failures
found during verification are fixed.** The tested editor, packaged-editor,
native and live scenarios pass. This is coverage of the scenarios below,
not a guarantee about every possible mod combination or platform.

## Build and evidence

- Base source commit: `7be2dd7c27fd402343cb906a4337a0dde2cf285e`.
- Host: Linux x86-64; native 32-bit `tmp/pc/game32/memories-pc`, rebuilt with
  `python3 tools/pc/build.py` before the checks.
- Game SHA-256: `39311d16f312ff4f7b297ccba024434ee03cf6fe56a2f292a3f373ef47aa8927`.
- Packaged `fm-editor` SHA-256:
  `95b7ca0f8787c604a73eb5efd79f5b7a88e8a182896825c13078c2f0a68eced8`.
- The player's supplied game files were used for live checks. Test mods,
  settings, saves, recovery settings and screenshots were isolated under
  `tmp/pc/editor-verification-20261010/`.
- GUI tests ran on Xvfb at 1600×1000. Live suites used separate displays.

The evidence folder is local and ignored by Git. It contains `unit-fixed.log`,
`package-fixed.json`, `native-fixed.log`, `fixed/live-results.json`, the
individual suite logs, and each suite's game logs, exported mods and screenshots.
`fixed/` holds the 19 live suite reruns after the gameplay fixes;
`values-repeat-fixed/` holds the repeated duel endings. Earlier failed runs
remain available for comparison.

## Editor checks

`python3 -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc -v`:
**601 tests passed, no skips**. This includes every-tab/button smoke tests;
form validation; sorting, search and cross-tab card links; text and card-view
previews; conversions and custom effects; fusion bulk operations; equip and
ritual controls; duelist rosters, pools and fixed decks; all UI pages;
starter decks and weighted pools; map routes and artwork; values; star rules
and icons; packs and simulations; mod metadata; conflicts; importers;
file dialogs; theme/scaling; undo/redo; recovery and save backups.

The every-button smoke test cancels file selections and closes dialogs.
The feature-specific tests exercise their accepted inputs and saved results;
pressing every button alone would not establish those behaviors.

`./fm-editor self-test --output <report>`: **passed**, all 14 tabs and the
four UI pages (`title`, `menu`, `duel`, `board`), card/art editing and
export/reopen.

The targeted native CTest run: **20/20 passed**, covering tables, fusion
rules, duelists, starter decks, stars, card stars/effects, packs, password
data, card notes/drops, UI/title/card layouts, overlaps, starchip prizes,
the hard-mode AI adapter, GTE, ordering tables, PGXP and the scratch-sweep fixture.
`make basic-types check-g32` also passes.

## Live coverage by tab

| Tab | What was exercised in the running game | Result / evidence |
| --- | --- | --- |
| Cards | Added/replaced cards, all 20 monster types, magic-to-monster conversion, converted equips/rituals, all 33 retail magic effects, trap thresholds/triggers, counted monster effects, CPU decisions after save/reopen, password purchases/prices and viewer | Passed in `card_types`, `magic_effects`, `trap_effects` (normal/hard), `editor_mods` (normal/hard), `monster_for_each`, `card_passwords`; all five replacement-trap scenarios pass |
| Art | Exported card textures; cyan imported Blue-Eyes artwork visible in the live card viewer, with retail comparison | Passed in `editor_round_trip`, `fixed/editor_tables` |
| Fusions | Added recipe produces Blue-Eyes; removed retail recipe produces the last input card; disabled mod produces retail results | Passed in `fixed/editor_tables`; additional fusion gameplay in UI suites |
| Equips | Legendary Sword gains Blue-Eyes as a target and adds 500 points; disabled mod adds zero; converted equip used in battle | Passed in `fixed/editor_tables`, `card_types` |
| Rituals | One to five tributes, hand/field/both, player and CPU, native and interpreted effects, hard-mode CPU | Passed in `ritual_tributes`: 32 native + 4 hard-mode + 32 interpreted + 4 interpreted hard-mode checks |
| Duelists | Added opponents/pages/slots/portraits, renamed retail opponent, fixed/weighted decks, drops, unlocks, ranks and custom LP | Passed in `editor_duelists`: 26 checks |
| UI | Title/menu artwork and actions; duel layout; board textures/tints on different fields; card-bar parts, colors, hiding and spacing; internal 1×/2× and widescreen rendering | Passed: `editor_ui` 74, `editor_board` 41, `editor_menu` 31, `editor_cardbar` 86 checks |
| Starter decks | New game receives exported fixed starter deck; weighted starter pools actually deal the deck | Passed in `editor_round_trip`; pool arithmetic and controls in editor/native suites |
| Map | Edited camera and entire route table present in live overworld RAM; imported magenta name-panel artwork rendered; disabled mod restores retail | Passed in `fixed/editor_tables`; terrain/sprite import/export and route controls in editor suite |
| Values | Player/opponent LP, stat cap, Crush Card threshold, spell penalties, Swords turns, rank score, all prize letters, deck copy limit and initial starchips, with retail comparison | Full `fixed/editor_values` run passes; 20 Exodia and 20 deck-out runs pass in `values-repeat-fixed` |
| Guardian Stars | Edited Mars/Jupiter matchup produces 700 battle damage between equal-stat monsters | Passed in `fixed/editor_tables`; names/icons/custom stars/choice modes/bulk rules covered by editor/native tests |
| Packs | Editor-created pack spends exactly 37 starchips and awards exactly three Blue-Eyes; disabled mod spends/awards nothing; guarantees, ownership limits, chest capacity, progress and state replay | Passed in `fixed/editor_tables`, `packs_game`, editor/native suites |
| Tower (added 2026-10-11, below) | A three-floor tower with story, a tower-only duelist, rules, rewards and checkpoints, played in the game: menu button, floors won and lost, LOAD at the checkpoint, the CPU kept from fusing, the duelist let out into Free Duel, the tower cleared | Passed in `tests/pc/tower/tower_e2e.py` (25 checks); see [Tower mode](tower-mode.md#tests) |
| Mod info | Metadata/settings export and game accepts the generated mod; save/reopen preserves the manifest | Passed in `editor_round_trip`, packaged/editor tests; does not assert every code-mod setting consumer |
| Conflicts | Invalid manifests, loader compatibility, overlap detection/load ordering and navigation to conflicting edits | Passed in editor suite and native overlap test; this tab itself has no gameplay action |

`editor_tables_runtime.py` was added for the live behavior gaps previously
covered only by manifest presence. Its **15 checks pass**, and its screenshot
color assertions verify card and map artwork on-screen, rather than merely
verifying that texture files loaded.

## Resolved gameplay regressions

### Exodia ordering-table corruption

The initial Values run crashed in `make_packet`, and a repeat crashed in
`GsSortOt` with the Values mod disabled. Diagnostics caught the first invalid
link before corruption: the interpreted Exodia module submitted priorities
such as 4,117, 5,690 and 6,319 to a 4,096-entry table. Those links overwrote
neighboring ordering-table entries and descriptors.

The native LIBGS packet sorter now bounds the index to the table's endpoints.
Valid priorities retain their original links. Out-of-range ray polygons still
render, sorted at the corresponding endpoint, instead of corrupting memory.
This deliberately changes the native port's handling of invalid priorities.
Temporary crash diagnostics and SDK comparison instrumentation were removed.

`tools/pc/test_libgs_priority.py` exercises the actual sorter with valid
boundaries, the observed failing priorities, nonzero offsets and a one-entry
table. It checks packet links and sentinels throughout the adjacent memory.
The fixture **fails against the base revision** and **passes with the fix**;
Linux CI runs it without requiring a game disc.

The full Values suite passes after the fix. The repeated ending check uses
ten deterministic RNG seeds in fresh games for each mod setting:
**20 Exodia presentations and 20 deck-out endings pass**, including rank
scores and starchip prizes. No rendering crash occurred.

Evidence: `gs-priority-baseline.log`, `gs-priority-fixed.log`,
`gs-probe-0/retail-ends/game.log`, `gs-caller-0/mod-ends/game.log`,
`values-repeat-fixed.log`, and `fixed/editor_values.log`.

### Replacement traps and lifted battle participants

Battle setup lifts the attacker and defender into separate display objects
and clears their field records' occupied bits. The previous trap completion
check treated those bits as evidence of destruction. A healing trap therefore
cancelled combat and removed the attacker: CPU LP went **8,000 → 8,200**,
rather than the expected **8,000 → 8,050**.

Explicit `DuelCard_RemoveFromField` calls now mark participant destruction;
battle setup's temporary deactivation does not. A harmless trap lets combat
resume and queues its normal triggers once. Custom destruction also considers
the lifted participants, which Crush Card's field walk cannot visit. The
abort path releases the removed battle objects and restores surviving cards.
No save-state fields were added.

The existing regression fixture now reaches the field phase before attacking
and explicitly gives the attacker its intended 50 ATK. Its **five scenarios
pass**: direct healing, direct attacker destruction, defended healing,
defender-only destruction, and destruction of both participants. Healing
checks the trap's +200, ordinary -50 battle damage, exactly one -100 combat
trigger and the surviving attacker. Destruction checks unchanged CPU LP and
which participants remain.

Evidence: `trap-expanded-3.log`, its before/after JSON and screenshots under
`trap-expanded-3/`, and the final `fixed/replacement_trap_combat` rerun.

## Re-running the added live checks

```sh
python3 tools/pc/build.py
xvfb-run -a -s '-screen 0 1600x1000x24' \
    python3 tests/pc/editor_tables_runtime.py --out tmp/pc/editor-tables
python3 tools/pc/test_libgs_priority.py
xvfb-run -a python3 tests/pc/replacement_trap_combat_runtime.py --out tmp/pc/replacement-traps
xvfb-run -a python3 tests/pc/editor_values_runtime.py --parts ends --end-repeats 10
```

For editor and other live checks, see the FM Editor guide's Tests section.
Separate Xvfb display numbers and output folders should be used for concurrent
runs. This environment's `/tmp` was full; setting `TMPDIR` to an empty folder
on the workspace filesystem allowed the packaged check to run successfully.

The broader native CMake build also encountered existing GCC
`-Werror=format-truncation` errors in `src/pc/saves/save_slots.c`. The targeted
editor-related targets built and their tests passed; the full native suite
is not reported as passing.

This run covers Linux native gameplay and the Linux packaged editor. It
does not verify Windows/macOS/Android releases, every mod combination, or
the optional comparisons against an older baseline executable. Some editor
features, such as map terrain import/export, advanced star choice/icon
variants and importer workflows, have editor/native test evidence but no
new live scenario for every variant in this run.

## Addendum 2026-10-11: the Tower tab

The editor has a fifteenth tab, **Tower** (`tower_tab.py`, `tower.py`): a
mod's `"tower"` (notes/tower-mode.md) and its duelists' `"tower_only"`. The
packaged `self-test` now selects all 15 tabs, builds a tower of one floor on
the Tower tab and checks that the export carries it with `"min_api": 14`.
`tests/test_tower.py` covers the tab (showing a tower, committing it untouched
as written, editing a floor, adding, moving and removing floors, the
tower-only list, the unlock conditions, turning the tower off, floors and
fields nobody touched keeping the mod's own spelling), the story text form's
round trip (line breaks, speakers with portraits, plain words that look like a
speaker's), the deck text form, the checks against `tower_config.c`'s keys, and the manifest
round trip. The in-game end-to-end run is `tests/pc/tower/tower_e2e.py`, with
the tests' tower mod (`tests/pc/tower/tower-test`), written by hand in the
form the tab writes.

Since 2026-10-12 the tab also edits a story's **stage** (notes/tower-mode.md,
Story): the tower's default `scene` and `dim`, and a Stage box that writes a
story's bracketed lines (`[scene: torch corridor]`, `[left: 1 expression 2]`,
`[right: opponent]`, `[right: tower/hero.png flip]`, `[pan: 64 0 30 wait]`)
into the story last clicked, before the cursor's line, with pictures of the
chosen scene and character made from the player's disc in memory
(`tower_art.py`; nothing of the disc's is written). A PNG picked from outside
the mod's folder is copied into its `tower/` when it is saved.
`tests/test_tower.py` adds the stage's text form and its round trip (a scene
by name, number or `"none"` read as the same; a mod's own spelling of its
stage kept through the tab), its checks, the scene names and the stage's
keys against `tower_config.c`, and the pictures from an archive's bytes. The
packaged `self-test` sets the tower's scene and puts a campaign character and
a PNG on a story's stage, and checks the export carries both, the PNG in the
mod's folder.

Round 3 (2026-10-12): the tab explains itself. **How to build a tower...**
opens a step-by-step guide (`tower.GUIDE`), **Start from an example** fills
in a working tower of three floors (`tower.example_tower()`, which the
checks read without a note), the options carry tooltips, and Help has a
**Tower mode** entry. A floor has **Unlock this opponent in Free Duel when
beaten** (`"unlock_opponent"`, ticked by itself for a tower-only opponent and
written only when it differs) and **Also unlocks** picks duelists from a
list instead of free text. The tower has **Leaving** (`on_leave`), **Cards a
win** (`drops`), **Allow save states in the tower** and **Allow cheats in the
tower**. `tests/test_tower.py` adds the guide and the example, the rules of
the run written only when they differ from the defaults, and the unlock
checkbox and picker. Window pictures of the tab (the guide, the options, a
floor's unlock) are taken by PrintWindow, the editor's window alone.

