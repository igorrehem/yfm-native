# Tower mode

A mod can add a **tower**: a run of duels, its *floors*, that the title's
second menu offers once the mod is on. Each floor is an opponent with a field,
a deck, starting LP and rules of its own (no fusions, no equips), a reward and
lines of story before and after it, told as the campaign tells its own: in
its stone-framed box, over a scene, with its large characters on top (or a
mod's own pictures of both). A save keeps how far it climbed. Without a tower mod the
game is the same, frame for frame (checked against a build without tower mode:
the title's two menus, the cursor walked through them).

```json
{
    "id": "shadow-tower",
    "name": "The Shadow Tower",
    "min_api": 14,
    "duelists": [
        {"id": "ghost", "copy": "Simon Muran", "name": "Ghost Simon", "tower_only": true}
    ],
    "tower": {
        "name": "The Shadow Tower",
        "label": "SHADOW TOWER",
        "unlock": "after_ending",
        "on_lose": "checkpoint",
        "scene": "torch corridor",
        "intro": {
            "scene": "seal shrine",
            "characters": {"left": "Simon Muran"},
            "lines": [
                "Three floors stand between you and the top of the tower.",
                {"text": "Win them all, my prince.", "speaker": "left"}
            ]
        },
        "ending": "The tower is yours.",
        "floors": [
            {
                "duelist": "Simon Muran",
                "checkpoint": true,
                "life_points": {"opponent": 4000},
                "reward": {"cards": ["Kuriboh"], "starchips": 25},
                "before": "Show me what you have learned.",
                "after": "Well fought. Climb on."
            },
            {
                "duelist": "shadow-tower:ghost",
                "field": "Dark",
                "no_fusions": true,
                "deck": {"Job-change Mirror": 20, "Monster Eye": 20},
                "before": ["Nobody fuses on this floor.", {"text": "Not even me.", "speaker": "shadow-tower:ghost"}],
                "after": "You may find me in Free Duel now."
            },
            {
                "duelist": "Seto",
                "no_equips": true,
                "reward": {"unlock_duelist": "Nitemare"}
            }
        ]
    }
}
```

The FM Editor writes all of it from its **Tower** tab, and the tests' own
tower is `tests/pc/tower/tower-test/mod.json`.

## Tutorial: a tower in ten minutes

The FM Editor's **Tower** tab does all of this without writing JSON: **How to
build a tower...** there walks through the same steps, and **Start from an
example** fills in a small working tower to change. By hand:

1. **A mod with a tower.** In a mod's `mod.json`, add `"min_api": 14` and a
   `"tower"` object with a `"name"` and a list of `"floors"`. One floor is
   enough: `{"duelist": "Simon Muran"}`. Turn the mod on in the game's Mods
   window: the title's second menu (CAMPAIGN to SAVE, after loading a game)
   has a **TOWER** button.
2. **Floors.** Each floor is a duel, bottom first. Give it a `field`,
   `life_points` (`{"opponent": 4000}`), rules (`"no_fusions": true`,
   `"no_equips": true`), or the opponent's own forty cards (`"deck"`). Mark
   the floors a loss sends the player back to with `"checkpoint": true`: the
   tower offers a save there.
3. **Rewards and unlocks.** `"reward": {"cards": ["Kuriboh"], "starchips":
   25}` is given the first time the floor is won. `"unlock_opponent": true`
   puts the floor's opponent on the Free Duel grid once beaten, and
   `"reward": {"unlock_duelist": "Nitemare"}` another duelist. A duelist your
   mod adds (`"duelists"`) with `"tower_only": true` is hidden in Free Duel
   until its floor is won (unless that floor says `"unlock_opponent":
   false`).
4. **When it opens.** `"unlock": "after_ending"` waits for the game's ending;
   `{"beat": "Seto", "wins": 3}` waits for a duelist beaten; without it the
   tower is open at once.
5. **Stories.** `"intro"`, `"ending"`, `"lose"` and a floor's `"before"` and
   `"after"` are lines of text, told on the campaign's stage: `{"scene":
   "throne room", "characters": {"left": "Simon Muran", "right":
   "opponent"}, "lines": [...]}` ([Story](#story)).
6. **The rules of the run.** `"on_lose"` (where a loss sends the player),
   `"on_leave"` (what leaving does to the climb), `"drops"` (the cards a won
   duel gives), `"save_states"` and `"cheats"` ([The rules of the
   run](#the-rules-of-the-run)).
7. **Try it.** The Mods window lists anything the game reads otherwise than
   meant (a misspelt key, a duelist it cannot find); the FM Editor's status
   line above the Tower tab shows the same.

## What the player sees

The second menu (CAMPAIGN to SAVE, once a game is loaded) has one more button,
the tower's `label` (`TOWER` without one), in the entries' look. While the
tower's `unlock` does not hold for the save loaded, it is drawn **dimmed** and
choosing it buzzes; it is never hidden, so the menu does not move as a save
opens it. The button is the mod's own `"<mod>:tower"` (made before the mod's
`menu` is read), so the mod's `menu` may move it, give it a picture, put it in
its `order` by `"tower"`, or hide it. A button of a mod's own may take the
action `"tower"` too, in the second menu only ([The title's menus](modding.md#the-titles-menus)).

The tower's screen is the game's own pieces, drawn by the game's own code:

- behind it, the title's wall (the main menu's package and
  `MainMenu_DrawFrontendBackground`), without the dark-to-light shade, so the
  boxes keep their window to the bottom;
- the game's text boxes (their dark window, letters, page arrow, choice cursor
  and sounds): the tower's name, `FLOOR 2 OF 3: Ghost Simon`, the floor's rules
  (`NO FUSIONS  LP YOU 100 COM 8000`, `CLEARED x1` once the top is reached),
  over **DUEL** and **LEAVE**; after a duel, `FLOOR 1 CLEARED!` with the reward
  and `CHECKPOINT` (four lines a page, a button between), or `YOU LOST. BACK
  TO FLOOR 2.`; at a checkpoint and after the top, `SAVE YOUR PROGRESS?` and
  then the game's own save (the port's slot menu);
- the stories, told as the campaign tells a scene's dialogue: the screen goes
  black and comes up on a scene picture with the campaign's stone-framed box
  at its foot, its large characters sliding in on the left and the right,
  the one speaking moving its mouth, page by page; then black again and the
  wall ([Story](#story)).

DUEL tells the floor's `before`, then the duel, armed as the Free Duel screen
arms one (the deck screen first); the game comes back to the tower after it.
A short deck gets the Free Duel screen's own answer. LEAVE (which the tower's
`on_leave` may make cost the climb) goes back to the
second menu, the cursor on the tower's button.

## The tower

| Key | Meaning |
|---|---|
| `name` | its name on the screen (the mod's id without one; 63 bytes) |
| `label` | the menu button's words, 31 bytes at most (UTF-8); `TOWER` without one |
| `music` | the screen's song, as `title`'s `music` takes it (`0x000`-`0xFFF`); the Free Duel screen's (`0x2C0`) without one |
| `unlock` | when the button opens it: `"always"` (the default), `"after_ending"`, or an object of conditions (below) |
| `on_lose` | `"checkpoint"` (the default): a loss sends the player back to the floor after the last checkpoint won; `"restart"`: back to floor 1, the checkpoints forgotten |
| `scene` | the scene of a story that names none ([Story](#story)); `"torch corridor"` without |
| `dim` | `true`: a character not speaking is drawn darker (the campaign only keeps it still) |
| `intro` | told the first time the tower is entered on a save |
| `ending` | told when the last floor is won |
| `lose` | told after a loss, before where it goes back to |
| `on_leave` | what leaving the tower does to the climb ([below](#the-rules-of-the-run)): `"resume"` (the default), `"checkpoint"` or `"restart"` |
| `drops` | the cards a won tower duel gives: 1 to 99, or `"player"` (Game > Card drops); 1 without it |
| `save_states` | `false`: no save state is saved or loaded while the player is in the tower |
| `cheats` | `false`: the Cheats menu and the Debug jumps do nothing while the player is in the tower |
| `floors` | the floors, bottom first, at most 99. At least one must be fought, else the mod has no tower |

**Several towers.** One tower a run: the **last mod in load order** that has a
`tower` has the menu's, and the one it replaced gets a note in the Mods window.
A save's progress in each tower is kept apart (below), so turning mods on and
off loses nothing.

### `unlock`

| Value | Opens |
|---|---|
| `"always"` (or none, or `{}`) | from the start |
| `"after_ending"` | once the save has seen the ending |
| `{"beat": ..., "wins": n, "story": n, "card": ..., "copies": n, "after_ending": true}` | when every condition holds: the duelists' own ([More duelists](more-duelists.md), read from the save's records, trunk and flags), and the ending when `after_ending` is `true` |

Written wrong (a word that is not one of those, a number that is not one), the
tower stays locked, so nothing opens by mistake; the Mods window says why.

**The ending, in the save.** `Main_RunCredits`
(`src/game/main_run_credits.c`, `0x8002DA1C`) begins the ending by setting the
low two bits of the save block's byte `0x3DE` (`save_state->field_3DE |= 3`,
`SAVE_DATA_CREDITS_FLAGS_OFFSET` in `save_data.h`), parking
`campaign_scene_index` at `0x30` and clearing the story flags `0x20`-`0x11F`,
and then asks for the save (`SaveData_RequestWrite`). Nothing on the US disc
reads the byte back (the Japanese release opens its PocketStation menu by it,
[the game](research/the-game.md#79-the-ending)); it is inside the secondary
checksum's range (`0x380`-`0x3EB`), so it is written with the save, and NEW
GAME clears the whole block (`NameEntry_Main` clears `0x801D0000`-`+0x3000`).
`"after_ending"` reads those two bits (`Tower_EndingSeen`). The story flags are
no use for it: the ending clears them, and `campaign_scene_index` is `0x30`
after NEW GAME too. A player who turns the ending's save down has not "seen
the ending" for the tower, as for the Japanese game.

### A floor

| Key | Meaning |
|---|---|
| `duelist` | the opponent: an id, a name, or an added duelist's identity (`"mod:id"`). A floor without one it can find is left out |
| `field` | `none` (the default, as Free Duel), `Forest`, `Wasteland`, `Mountain`, `Meadow` (`Sogen`), `Sea` (`Umi`), `Dark` (`Yami`), or 1-6 |
| `deck` | the opponent's deck: `{card: copies}` as a fixed deck is written, or a list of forty cards; exactly forty, else its own is dealt. It comes before a fixed deck of `decks` |
| `life_points` | the starting LP of both sides, or `{"player": ..., "opponent": ...}`, 1 to 65535. Between Game > Cheats > Starting LP (which wins) and a mod's `limits` |
| `no_fusions`, `no_equips` | `true`: nothing fuses, nothing equips, below |
| `reward` | `{"cards": [...], "starchips": n, "unlock_duelist": ...}`, given the **first** time the floor is won (`card` takes one card) |
| `checkpoint` | `true`: won, a loss later comes back to the next floor, and the tower offers a save |
| `unlock_opponent` | `true`: beaten, the opponent is on the Free Duel grid (a disc duelist gets its Free Duel flag, `0x6E0 + id`, on every win; an added duelist with conditions of its own is shown whatever they say); `false`: not, even a `tower_only` one. Without it, a `tower_only` opponent is let out and any other is not |
| `before`, `after` | told before the duel, and after a win |

A won duel moves the climb on; the top tells the `ending`, offers a save, and
sets the tower back to floor 1, its floors still won (rewards are not given twice), the
status counting the climbs (`CLEARED x2`). The usual drops and starchips of a
won duel come as in any duel. A tower duel is **not** a Free Duel: it is never
counted on the Free Duel grid's win/loss records (the Free Duel screen's
return flag `0x80` would), which is why the duelists' unlock has a `tower`
condition of its own.

**The rules are the game's own checks.** `no_fusions` and `no_equips` are
answered in `CardRules_Fusion` / `CardRules_Equip` and in `Duel_CheckFusion` /
`Duel_CheckEquip` (`src/game/duel_card_checks.c`), which the player's card
placement, the CPU's planning (`Ai_CompleteFusion`, `AiScript_FindEquipTarget`
and `ai_turn_action.c`) and the fusion helper all ask: a fusion of the
player's fails as an unmatched pair fails, and the CPU never plans one. A code
mod's answer to `MEMORIES_EVENT_FUSION` / `EQUIP` cannot overrule a floor's
rule. The rule holds only in the floor's own duel (armed by the tower, the
game in that duel or its 3D battle, on its way back to the tower), never in
Free Duel or the campaign.

`reward.unlock_duelist`: a duelist of the disc gets its Free Duel flag
(`0x6E0 + id`, as its "you won" text gives it; not the campaign's `0x1F + id`,
which the event script tests to choose scenes); an added duelist marked
`tower_only` is let out (below).

### Story

A story is told as the campaign tells a scene's dialogue: in its
stone-framed box at the foot of the screen, over a **scene** picture, with up
to two of its large **characters** standing on the box, one on the left and
one on the right. It is the campaign's own machinery doing it, so a retail
scene with a retail character is the campaign's frame, pixel for pixel (the
end-to-end test compares one with the campaign's first scene).

A story is one line of text, a list of them, or an object whose `lines` are
the list:

```json
"before": {
    "scene": "throne room",
    "characters": {"left": "Simon Muran", "right": "opponent"},
    "lines": [
        {"text": "My prince, he is here.", "speaker": "left"},
        {"text": "Show me what you have learned.", "speaker": "right"},
        {"text": "Outside, then.", "scene": "scenes/courtyard.png",
         "characters": {"left": {"image": "art/hero.png", "flip": true}}},
        {"text": "Look at the sky.", "pan": {"x": 64, "frames": 90}}
    ]
}
```

Each line is a page or more of the box (three lines of text a page, at its
width, a button between pages). What a line says about the stage holds from
that line on, until another line changes it; what the story object says is
its first line's.

| Key | Meaning |
|---|---|
| `text` | the words (UTF-8; letters the game and the mods' fonts lack are left out) |
| `scene` | the picture behind, from this line on (below). Another scene mid-story crossfades as the campaign's do |
| `characters` | `{"left": ..., "right": ...}`, the sides it names (below); a side it does not name stays as it was. A character that changes slides out and the new one in |
| `speaker` | who says it: `"left"` or `"right"`, a duelist (id, name, identity; the side showing its character), `"opponent"` (the floor's), or `"none"` |
| `portrait` | a small face beside the box as well: one of the campaign's 25 dialogue portraits, `0`-`24` (0 is Simon Muran), `"speaker"` for the speaker's own (its Free Duel portrait), or `"none"` |
| `pan` | `{"x": ..., "y": ..., "frames": ..., "wait": ...}`: the scene's view moved to x (0-576), y (0-96) over that many frames (60 without; 1-3600), the words waiting for it with `"wait": true`. A wide scene (100-141, 200-212) has room to move; a mode-0 one, 320 wide, shows black past its edge |

**Defaults, all overridable.** A story that names no scene is told over the
tower's `scene`, else `"torch corridor"` (22). A floor's `before` and `after`
have the floor's opponent's campaign character on the right and are its words
(`speaker` `"opponent"`); `intro`, `ending` and `lose` have nobody on the stage
and are nobody's. A small portrait shows only when a line asks for one, or
when its speaker is a duelist without a character on the stage (then its own
face, as the old portrait-only stories had it); `"portrait": "none"` keeps it
off. The speaker's character moves its mouth with the words and blinks; the
other one keeps still, as the campaign does it (`F6 id 20`/`21`). **The
campaign never darkens the one not speaking**: the tower's `"dim": true` does,
an option of the port's own.

**A scene** is one of the disc's pictures, by name or by number, or a PNG of
the mod's:

- mode 0, the 320 x 160 backgrounds the campaign tells its dialogue over, by
  name or 0-41: `black` (0), `palace gate`, `palace chamber`, `jungle temple
  door`, `card shop`, `colonnade hall`, `moonlit colonnade`, `collapsed
  ruins`, `classroom`, `tournament lounge`, `card collection` (10), `shop
  street`, `temple ruins`, `destroyed town`, `ruined altar room`, `ruined
  chamber`, `sunlit ruined hall`, `fiery valley gate`, `seal shrine`, `green
  pyramid`, `green mausoleum` (20), `obelisk avenue`, `torch corridor`, `cliff
  temple`, `night temple stairs`, `jungle pyramid`, `green shrine`, `dusk
  tower`, `altar hall`, `desert sphinx`, `sphinx shrine` (30), `meadow
  temple`, `twin statue shrine`, `throne room`, `hall of fires`, `eye
  chamber`, `town at night`, `night balcony`, `golden doors`, `golden door
  chamber`, `statue gallery`, `burning pyramid` (41); `"none"` is black;
- modes 1 and 2, 100-141 and 200-212: the campaign's wider stills, each with
  its own figures drawn in (Heishin with the lamp, the robed mages, the
  Millennium items, the tournament's stadium...);
- a PNG (any size, made into 320 x 160 at 8 bits, its clear parts black), a
  path inside the mod. Above the console's resolution the PNG itself is drawn,
  at its own resolution (the texture pack's made images, [image
  remaster](image-remaster.md)).

The number is the game's own image id written in decimal: its digits are
the id's hexadecimal ones (BCD), 22 is `0x022`, 139 is `0x139`. The FM
Editor's Tower tab shows each one as a picture, made from the player's disc.

**A character**, a side's value:

- `"none"`: nobody;
- a number, 1-64: the campaign's large character of that number (1 Simon
  Muran, 4 Seto, 12 the prince...; 0, 5, 11, 39, 40 and 41 are empty on the
  disc). The Tower tab shows each one;
- a duelist (id, name, identity), or `"opponent"`: the character the
  campaign shows that duelist as before its duel (an added duelist: its
  base's). The villagers and the five shrine mages have none;
- a PNG, a path inside the mod: a picture of up to 256 x 256 (a larger one is
  shrunk to fit), its clear parts clear, standing on the box as the
  campaign's do -- its middle over the side's place, its bottom edge just
  under the box's top, or, taller than the 178 rows above it, its top at the
  screen's and the rest under the box. It is drawn at the console's resolution;
- an object: `{"character": 4, "expression": 2}` (a campaign character's
  expression 0-3, changed in place on a later line), `{"duelist": "Seto"}`,
  `{"image": "art/ghost.png", "flip": true, "duelist": "opponent"}` (the
  PNG turned to face the other way; its duelist the one whose lines it
  speaks).

**Limits.** Two sides, no middle (the campaign has two places; the third
record is the small portrait). One character may stand on one side at a
time (the game finds them by number). A story shows at most five pictures of
the mod's (the cache of characters has five places), and a tower has at most
96 PNGs, scenes and characters together. A story is told in one box, so its words are at
most about 12000 letters, each line counting 48 more for its stage's codes; the lines past
that are left out, noted (and should a box still fill, the story ends there, logged). A
line without words is left out, its stage with it.

**How it is drawn.** It is the campaign's scene machinery, driven from the
tower's screen rather than from the event script (`Script_RunTick`):

- the stage comes up from black: `Campaign_LoadScenePackage` (the box's
  stone frame, phase 0 of the package at VRAM (832, 0), drawn by
  `Campaign_CreatePrimaryDisplayObject`; the 25 portraits, [dialog portrait
  bank](dialog-portrait-bank.md); the scene slots), then the scene by
  `ScriptImage_RequestTransfer` and `ScriptImage_RebuildObjects`, as
  `Script_OpLoadImageScene` loads one; the title's wall is gone meanwhile (the
  scene's palette, (0, 240) 256 x 4, is inside the wall's), and back after;
- the story is one text in the box (`TextBox_Create`'s place, `0x10, 0xB0`,
  `0x120 x 0x30`, no dark window), in the game's codes: a character in
  (`F6 id 1x`, bit 0 the right, bits 1-2 the expression,
  `Text_HandleDisplayEffectCommand`), its expression (`F6 id 4e`), speaking
  or still (`F6 id 20`/`21`), out (`F6 id 80`), a small portrait (`F6 41+n`),
  another scene (`F7 05 id`: `func_8003767C`, then `Script_OpShowImage`, which
  `TextBox_BuildStep` dispatches as the campaign's text does), a pan (`F7 0B
  x y frames`: `func_8003771C`, `Script_UpdateViewportTween`). One text,
  because a new box resets the display-effect records (`TextBox_BuildStep`'s
  `func_80039E9C`), which would leave the characters' objects behind;
- another scene's crossfade copies the screen to VRAM (448, 256)-(767, 415),
  across the right side's character (640-831, 256-511): a right character goes
  out before it and comes back after, as the campaign's own scripts order it;
- a mod's scene has an image id no record of the disc's has (0x0A0 up, not
  BCD): `ScriptImage_RequestTransfer` asks the tower first (`#ifdef
  MEMORIES_PC`) and the tower puts it where a mode-0 record streams, in that
  record's layout (words 0-127 of rows 256-415, the right 64 texels in rows
  416-495), from the game's memory, so the texture pack's tags of those words
  are cleared or found by their bytes, never left over;
- a mod's character is one of the characters the disc keeps empty (0x27,
  0x28, 0x29, 0x0B, 0x05), and `func_8003A560` asks the tower to fill its
  cache slot (`#ifdef MEMORIES_PC`) before it would read the disc: the sheet,
  the two palette rows and a parts bank as the disc's records have them, so
  it slides, speaks and goes as theirs do;
- the stage goes down to black after the last page, the characters released
  (`func_80039FD4`), the scene's objects and the frame too, the wall up again.

Without a tower story on the screen the two hooks find nothing to do: the
ids they answer are none of the disc's.

## The rules of the run

All of them the tower's own, set in `mod.json` or on the Tower tab; each
holds only while the player is in the tower (its screen, its stories, its
floors' duels) and nowhere else in the game.

**`on_leave`: leaving.** `"resume"` (the default) keeps the climb as it is:
the player comes back to the floor they left from, as before. `"checkpoint"`
sends the climb back to the floor after the last checkpoint won, and
`"restart"` back to floor 1 (the checkpoints forgotten; floors won stay won,
so rewards are not given twice). The default is `"resume"` because the
tower's deck screen comes before every floor anyway, so leaving is no
advantage of itself, and a player who leaves to rest should not lose the
climb unless the mod asks for it. With `"checkpoint"` or `"restart"`
nothing keeps a floor past the checkpoint:

- **LEAVE** banks the climb as it leaves (`Tower_Bank`);
- **any other way out** (a Debug jump, the title's own reset) is banked as
  the tower is entered again from the title;
- **a save** -- the tower's own at a checkpoint, the title's SAVE, the
  game's memory card -- writes the banked climb to the save's file
  (`tower/<slot token>.txt`), whatever the climb in memory is, and a
  **load** reads it banked too. Quitting or resetting mid-run therefore
  comes back to the checkpoint at most;
- **a loss** follows `on_lose` as always.

Only save states could keep more; `"save_states": false` closes that too.
Under `"restart"` the tower still offers its save at a checkpoint: it keeps
what was won (the cards, the starchips, the floors won for their rewards
and unlocks), while the climb in the save's file starts at floor 1.

**`drops`: cards a win.** A tower duel's results screen gives the cards the
game's Free Duel does: the console's one card, or more with the player's
Game > Card drops (up to 99). In a tower duel `drops` is the count instead:
1 by default, so a player's 99 does not inflate a tower; `"player"` follows
the setting. The floor's `reward` is given as well. Inside the tower the
tower's value wins over any other count of drops, the game's or another
mod's.

**`save_states`: false.** No save state is saved or loaded while the player
is in the tower, whichever way it is asked for (the hotkeys, the menu's
Save state / Load state, `MEMORIES_AUTOSAVE`, the control channel): the
game's state code refuses it (`src/pc/guest/state.c`, and the macOS ARM64
build's `translated_state_backend.c`, ask `Tower_Guard`) and says why in a
notice (the control channel gets the reason). Outside the tower they work
as usual -- but a state saved there holds the climb as it was then, so with
`"save_states": false` loading one keeps the climb as it is now
(`Tower_Frame` puts it back after the load): no loss is undone and no
checkpoint regained that way.

**`cheats`: false.** While the player is in the tower: Game > Cheats >
Starting LP and Show CPU's hand do not apply (the duel begins at the floor's
LP or 8000, the CPU's hand stays face down), Give cards, Unlock all Free Duel
CPU duelists and Set StarChips are refused with a notice, and so are, during
a floor's duel, Debug > Jump to, back to the title and Game > Restart game
(which would leave it without its loss; from the tower's own screen a jump is
a way out as LEAVE is, and `on_leave` banks it the same). Free spending is the password shop's alone. The game's other rewinds
are gone (the old Rewind setting is retired).

## Duelists of the tower's alone

A duelist's `unlock` takes `"tower": true` (the tower won to its top) or a
floor (`1` up) won on the save, in **this run's** tower (the last mod's; with
no tower on, the condition does not hold); `"tower_only": true` on an added duelist keeps
it off the Free Duel grid until a won floor fights it (unless that floor says
`"unlock_opponent": false`) or names it in its reward's `unlock_duelist`
([More duelists](more-duelists.md)). The tower fights it whatever its unlock
says.

## A save's progress

The climb of each tower is the save's: the next floor, the checkpoint, the
floors ever won (for rewards and unlocks), the climbs to the top, whether the
intro was told.

- It is **game data** (`gTower`, `src/pc/game/zz_tower_storage.c`), so every
  save state has it, and a state saved in a tower duel keeps its floor and
  rules, and a state saved in the middle of a story comes back to the same
  page on the same stage (the scene, its characters, the cache of mod
  pictures they stand for are all in the game's memory). It is the last game
  unit, so no game variable moves; it does make the game's zeroed variables
  longer (`gTower` is about 16.5 KB, a whole story's text; the stage's upload
  buffers about 45 KB more), and a state restores those only at this build's
  size, so a save state made by a build before this one loads without them,
  as after `drops.c` came in (memory card saves are not touched).
- Beside the save, as `tower/<slot token>.txt` in the user folder, read when
  the save is loaded and written when it is saved (as the card packs' progress
  is), one section per tower by its mod's id:

  ```text
  tower shadow-tower
  identity 1A2B3C4D
  owner 0012ABCD
  floor 1
  checkpoint 1
  completions 0
  flags 1
  cleared 0
  end
  ```

  `identity` is the mod's id and the tower's name: the same mod with another
  tower begins again. `owner` is the save's duelist code; NEW GAME is a save
  with no climb. A section of a tower whose mod is off this run is kept as it
  was and written back, and a save state carries those lines too (chunk
  `tower-foreign`). Saved in a run with no tower at all (its mod turned
  off), the save's file follows it to the slot it is saved to, untouched (a
  save state knows which save was loaded last, chunk `tower-loaded`). The
  file of a slot saved over goes when a save is written with a tower on or
  carried over; until then it is only left behind, read by no save.
- The climb counts when the game is **saved**, as everything else does: the
  tower offers a save at each checkpoint and after its top. A loss sends the climb in memory
  back at once; LOAD gives the save's.

## The screen's words

The port's own strings `FE70`-`FE7F` ([translation](translation.md)), which a
translation may give, letters and spaces and `%d` / `%s` only: `FE70` FLOOR %d
OF %d: %s, `FE71` DUEL, `FE72` LEAVE, `FE73` NO FUSIONS, `FE74` NO EQUIPS,
`FE75` LP YOU %d COM %d, `FE76` CLEARED x%d, `FE77` FLOOR %d CLEARED!, `FE78`
%d STARCHIPS, `FE79` %s UNLOCKED, `FE7A` CHECKPOINT, `FE7B` THE TOWER IS
CLEARED!, `FE7C` YOU LOST. BACK TO FLOOR %d., `FE7D` SAVE YOUR PROGRESS?,
`FE7E` YES, `FE7F` NO. A line is the box's width: 32 letters.

## Which game

A tower needs mod API 14 (`"min_api": 14`, [Which game a mod
needs](modding.md#which-game-a-mod-needs)): `tower`, a duelist's `tower_only`
or `unlock` `tower`, a menu item's action `tower`. An older game would play the
mod without its tower.

## How it is built

| Where | What |
|---|---|
| `src/pc/tower/tower_config.c` | the key as read, with its notes; the progress and its file format |
| `src/pc/tower/tower.c` | the unlock, the floor's rules, LP and deck in its duel, the duelists' conditions, the save's file and the state chunk |
| `src/pc/tower/tower_screen.c` | the screen: its steps, text, a story's stage in the game's codes, the duel's arming and its result |
| `src/pc/tower/tower_art.c` | a story's PNGs made into the game's pictures (a scene record, a character's sheet and parts bank) |
| `src/pc/game/zz_tower_storage.c` | `gTower`, and what only game code reaches: the box's layout reset, the title's wall, the stage up and down, a mod's scene put in VRAM, a mod's character in the cache |
| `src/game/script_image_objects.c`, `display_effect_resource_setup.c` | the two hooks (`#ifdef MEMORIES_PC`): a mod's scene id, a mod's character |
| `src/pc/guest/state.c`, `src/pc/platform/title_jump.c`, `menu.c`, `src/pc/debug/cheats.c`, `src/pc/cards/drops.c` | the rules of the run: save states, the Debug jumps, the Cheats menu and the cards a win asking the tower (`Tower_Guard`, `Tower_CheatsOff`, `Tower_CardDrops`) |
| `src/game/main_mode_runners.c` | mode 13, the game's unused developer-mode slot, runs the tower's screen; `Main_Loop` and the mode table stay the game's, so older save states still load |
| `src/game/main_apply_menu_selection.c` | the button's choice (12, none of the game's) |
| `src/pc/platform/title_config.c`, `title_menu.c` | the button, the action, dimmed while locked |

Every step the screen takes is logged with `MEMORIES_TRACE=mods`
(`tower: status (floor 2, checkpoint 2)`, `tower: floor 1 won; next 1,
checkpoint 1`, `tower: fusion refused: 103 with 402 would make 22`...), which is
what the end-to-end test follows.

## Tests

- `pc_tower` (`tests/pc/tower_test.c`): the key read, its defaults and every
  note, the last mod's tower winning, a duel's result moving the climb (a
  checkpoint, a loss, `restart`, the top), the progress file with other
  towers' sections.
- `pc_tower_game` (`tests/pc/tower_game_test.c`): `unlock` (always,
  `after_ending` by byte `0x3DE`, conditions), the rules, LP and deck only in
  the tower's own duel, the duelists' `tower` and `tower_only`, the save's
  file across loads, NEW GAME, slots and the state chunk.
- `pc_fusion_rules`, `pc_duelists`, `pc_title_config`: the rules through
  `CardRules_*` and the `Duel_Check*` the CPU asks, a code mod's answer
  overruled; the duelists' conditions; the button and the action.
- `pc_tower` also reads every key of a story's stage, right and wrong, its
  defaults and the story's cut.
- `tools/pc/fm_editor/tests/test_tower.py`: the Tower tab, the stage's text
  form and its round trip, the checks, the scene names and keys against
  `tower_config.c`, the pickers' pictures from an archive's bytes.
- `tests/pc/tower/tower_e2e.py`, in the running game through the control
  channel ([agent control](agent-control.md)), with the tests' tower: the
  button, floor 1 won (its reward, the save at its checkpoint), floor 2 lost
  (the player's fusion refused, the CPU's deck of fusion material never
  fusing while a control run without the rule fuses Summoned Skull), back to
  the checkpoint; a new process LOADs and is at floor 2; the tower-only
  duelist out of Free Duel until floor 2 is won; floor 3 (an equip refused)
  clears the tower, its ending told and the climb saved, Nitemare on the grid; `after_ending`
  dimmed and buzzing until the save's byte says the ending was seen; every
  story (intro, before, after, lose, ending) told on a stage; the stage
  itself (a phase of its own, with PNGs the test draws): the campaign's first
  scene (Simon Muran at the palace gate) as the campaign shows it, against a
  NEW GAME run's frame -- no pixel above the box differs, only the words in
  it --, a mod's character on the right, a mod's scene mid-story with that
  character out and back whole, a pan, a save state taken mid-story loading
  to the same page, a campaign portrait, the stage down after, and `"dim"`;
  the rules of the run (screenshots in a `round3` folder): `on_leave`
  `"checkpoint"` (a floor won past the checkpoint gone after LEAVE and after a
  jump to the title) and `"restart"` (floor 1 after LEAVE, past a
  checkpoint), `unlock_opponent` (`false` keeps the tower-only Ghost Simon
  out of Free Duel once beaten, `true` gives Rex Raptor his Free Duel flag),
  `drops` 5 with Game > Card drops at 99 (five cards), and `"save_states":
  false` with `"cheats": false` (a state neither saved nor loaded on the
  intro's stage, the status or in the duel, a duel at 8000 with Starting LP
  at 9999, no jump out of it; a state saved outside the tower as usual);
  and, without the mod, the title's menus the same frames as a build without
  tower mode.

  ```sh
  python tests/pc/tower/tower_e2e.py --exe tmp/pc/game32/memories-pc.exe \
      --baseline <a build of master>/memories-pc.exe --out tmp/pc/tower-e2e
  ```
