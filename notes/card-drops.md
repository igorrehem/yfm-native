# Card drops

**Game > Card drops** sets how many cards a won duel deals: 1 (the console's)
to 99. Drag the slider, or open the menu with the keyboard and step it one at
a time with Left/Right. The setting is saved as `card_drops`;
`MEMORIES_CARD_DROPS=N` sets it for one run. A mod may lock it
([below](#a-mod-that-sets-it)).

## A mod that sets it

A mod's `mod.json` may fix how many cards every won duel deals, whatever the
player chose:

```json
"limits": {"card_drops": 5}
```

Any whole number from 1 to 99, Game > Card drops' own range (the FM
Editor's Values tab, Rewards, **Cards a win deals**). While the mod is
applied, Game > Card drops reads `Card drops (set by <the mod's name>)`,
greyed, with the slider at the mod's number, and cannot be changed. The
player's own value is not touched: it stays saved as `card_drops`, and
when the mod is removed (a restart, as for every `limits` key) the menu and
the duels have it back.

- **Several mods** that set it: the one applied later wins, as for every
  `limits` key (the mods' load order, [When mods
  overlap](modding.md#when-mods-overlap)). The mod whose different number
  it replaces gets a note in the Mods window naming it,
  `limits: "card_drops" 5 is not used: other-mod, applied later, locks it
  at 7`, and the Mods window's overlaps and the FM Editor's Conflicts list
  both.
- **A wrong value** (0, 100, `"5"`) is a note in the Mods window
  (`limits: "card_drops" is at most 99; left out`, `... is at least 1; left
  out`, `... is a whole number, 1 to 99, without quotes; left out`) and the
  key is left out: the player's setting decides.
- **`MEMORIES_CARD_DROPS=N`** is the player's setting for one run, as
  before, so a mod's lock wins over it too. Tests use that: the player at
  99 and a mod's 5 deal 5.
- **Code mods** read the lock with `host->limit(host, "card_drops")`: the
  number, or 0 while no mod sets it and the player's setting decides.
- A game older than mod API 13 would leave the key out and deal the
  player's count, so a mod that sets it says `"min_api": 13` (the FM Editor
  writes it).

The cards themselves come as below, from the same rolls: only how many
changes.

## On RESULTS OF DUEL

The SPOILS page is the game's own: it shows one card, which the game awards
as always. The other cards get pages of their own, between SPOILS and the
statistics:

SPOILS → drops page 1 … drops page N → statistics → SPECIAL ARTS → SPOILS

Left goes the other way. With one card, or after a duel with no reward, only
the game's three pages remain.

The added pages use SPECIAL ARTS' seven plates and the game's text box, so HD
text and mod fonts apply to them too. Each plate is one card: its number, its
name (cut with `...` when it would run into the columns), `xN` for more than
one copy, and **NEW** when you had no copy of the card in your deck or chest
before the duel. New cards come first, then the rest, each by number. The
heading gives how many cards the pages hold and which page of how many this
is. A translation can give NEW and the heading in its words (strings
`FE00`-`FE03`, [translations](translation.md#the-ports-own-strings)).

The card SPOILS shows is never listed again. A page can still show the same
card when the table dealt another copy of it, since that copy is a separate
card.

## How the cards are dealt

Every card comes from the game's own roll, `Duel_SelectCardDrop`, on the
table SPOILS uses (the opponent and your rank), including tables edited by
mods and mod cards that replace retail ones. At 2 or more the random numbers
are drawn in the community drop mod's order: one draw thrown away, then for
each card six draws and the roll, `1 + 7N` in all. The last roll is SPOILS'
card. For the same seed you get the same cards as on that mod's patched discs
(the static recomp's MODS > CARD DROPS matched this order too). At 1 the game
makes its single roll, as on the console.

The cards are awarded when you leave the screen, all but SPOILS' card first,
through `Duel_AwardCard`, so mods see `MEMORIES_EVENT_REWARD` for each card.
SPOILS' card is awarded last and is the newest of the chest's 16 recent cards
(its New! marks). A card already at the chest's 250 stays at 250.

## Mods

Every card of a won duel, SPOILS' included, is one roll of the game's
`Duel_SelectCardDrop`, made by `CardDrops_Roll` (`src/pc/cards/drops.c`),
which `DuelScene_UpdateResultRewards` calls under `MEMORIES_PC`. A code mod
that hooks `Duel_SelectCardDrop` (mod API 4) therefore decides every card,
the added ones too, and sees the cards this duel already dealt in
`gCardDrops`. SPOILS' card is rolled last. Smart drops, which leaves out
the cards the player has three of, was a Game menu setting (`smart_drops`,
ignored now) and is a separate mod of that kind, not shipped with the port.

## Save states

The dealt cards and the page on screen are game variables
(`src/pc/game/drops.c`), so a state saved on RESULTS OF DUEL keeps them:
loading it shows the same pages and awards the same cards, whatever the
setting is by then. The setting only changes the next duel.

The file sorts after `card_storage.c` on purpose. Game units link in name
order, and a variable inserted before existing ones moves them, which makes
states from earlier builds fail to load ("game variable ... moved").

## Code

- `src/pc/cards/drops.c`, `drops.h`: dealing, awarding, page order and the
  page text; `CardDrops_Count`, a mod's lock or the player's setting.
- `src/pc/cards/tables.c` (`read_values`, `Tables_CardDropsLock`): a mod's
  `"limits"` `"card_drops"`, which mod set it, and the note when another
  mod's replaces it.
- `src/pc/platform/menu.c` (`update_card_drops_item`): Game > Card drops
  greyed and named after the mod while it is locked.
- `src/game/func_800218F0.c` (`DuelScene_UpdateResultRewards`): calls
  the roll, the award and the page turn, under `MEMORIES_PC`.
- `src/game/duel_result_runtime.c` (`Duel_ShowResultPage`): an added page
  takes SPECIAL ARTS' plates (resource variant 2) and string
  `CARD_DROPS_TEXT_ID` (0xFFFF), which `Text_Resolve` answers with the
  composed page.

The page uses the text codes the result strings use: `f8 01 dy` (new line
`dy` pixels down, signed), `f8 06 x16` (x), `f8 02 dx`, `f8 04 1|2` (the
small or large letters) and `f8 0A` color. Spaces are `f8 02 08` steps, not
glyphs. The text box can hold 255 glyphs, and a page keeps under 240.

## Verification

With the disc in `game/` and the game built, `python3
tools/pc/test_card_drops.py` wins a real duel (the smoke opening, then the
opponent's life points zeroed in a saved state) and checks that:

- with one card, Right from SPOILS reaches the statistics and one card is
  awarded;
- with twenty, Right opens the first added page, Left from SPOILS reaches
  SPECIAL ARTS, and Left from the statistics reaches the last added page;
- leaving awards twenty cards, from a state saved on the screen and with
  the setting set back to one, with SPOILS' card the newest.

`tests/pc/card_drops_test.c` (CTest `pc_card_drops`) checks the rolls:
1 + 7N draws for N cards, each from the pool, and one card the same as the
game's own roll; and a mod's lock: 5 and 99 over the player's 1 and 99,
the player's value back without the mod, the later of two mods, and the
values left out with their notes.

`python3 tools/pc/test_card_drops_mod.py` wins the same duel with mods in a
test user directory: a mod's 5 over the player's 99 deals 5, a mod's 99
over the player's 1 deals 99, the player's 99 is back without the mod, a
mod's 0 is noted and left out, and of two mods the later one's count is
dealt. It also saves the window with Game open on the locked row
(`menu-locked.bmp`) and without the mod (`menu-player.bmp`), `--menus` for
those two alone, and takes `--windows`, `--executable` and `--out` as
above (`tmp/pc/card-drops-mod-smoke/`).

`--windows` runs it on the Windows build under Wine; `--executable` names
another build (a `.exe` runs directly on Windows) and `--out` another folder.
Screenshots and frames are left in `tmp/pc/card-drops-smoke/`.
