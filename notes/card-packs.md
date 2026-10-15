# Card packs

A mod may sell booster packs: a pack costs starchips (and, if it says, cards
from the chest), deals a handful of cards from pools the mod writes down, and
turns them over one by one on the Password screen, in the game's own card, box,
letters and sounds. Nothing about the memory card's save changes.

The data is `src/pc/cards/packs.c` (`packs.h`); the screen is
`src/pc/cards/pack_shop.c` (`pack_shop.h`), reached from a few lines in the
Password screen's own code (`src/overlays/password/shop.c`,
`src/game/main_run_password_menu.c`). With no pack declared none of it acts:
the Password screen is the console's, byte for byte and pixel for pixel.

## The smallest pack

```json
"packs": [
    {"name": "Dragons", "price": 50, "cards": ["Blue-eyes White Dragon", "Baby Dragon", "Koumori Dragon"]}
]
```

That is a pack of five cards, each card as likely as the next, repeats
allowed, as many as the player can pay for, from the start. It is sold on the
Password screen behind △, shows its first card's art on the big card, turns its
cards over one by one, and uses the Password screen's own sounds.

`"packs"` may instead name a file of the mod, `"packs": "packs.json"`, holding
the list, or `{"packs": [...], "pack_shop": {...}}`. The file and the pack
images are part of the mods' signature, so a save state made with other packs
is not taken for this run's (`Mods_Signature`).

The packs of every applied mod add up, in load order. They are read once, when
the game starts, like the other tables: changing them needs a restart.

## Everything a pack may say

| Key | Default | What it does |
|---|---|---|
| `id` | the name, lower case, hyphens for the rest (`"Legend of B.E.W.D."` is `legend-of-b-e-w-d`) | the pack's key: 1-63 letters, digits, `_` or `-`. With the mod's id it is the pack's identity, `mod-id:id`, which the save's progress, `unlock` `opened` and other packs use |
| `name` | the `id` | up to 16 letters, the room between the list's ◄ and ► arrows; longer is cut, with a note. UTF-8: letters the game lacks come from the mods' fonts, as card names do |
| `description` | none | the first two lines (20 letters each) show under the name; □ shows it all |
| `image` | none | a PNG inside the mod: the big card's picture ("The screen", below); any size, cut to 102:96 from the middle |
| `image_style` | `"card"` | how the `image` shows: `"card"`: as the card's art, in the card's frame with the name on its plate, cut to 102:96 from the middle; `"full"`: the whole picture where the card is drawn, frame and all, as large as fits the card's 140x196 with its shape kept, in the middle (a booster pack's own picture) |
| `cover` | the first card of the rarest tier that has cards | the card whose art stands in when there is no `image` |
| `shop` | every shop | a shop's id or a list of them (`pack_shop` `shops`); `"*"` for all |
| `order` | the place it is declared in, across all mods | the list is sorted by it, ties by declaration |
| `price` | 100 | starchips, 0 to 999999; 0 is free |
| `cost` | `{"starchips": price}` | `"starchips"` (the price again; `cost` wins over `price`) and `"cards": {card: copies}` (up to 8 cards, 1-250 copies each): copies taken out of the chest as part of the price. The deck's copies are not taken |
| `count` | 5, or as many as `slots` | cards a pack deals, 1 to 40 |
| `cards` | | the pack's one pool: a list (a weight of 1 each) or `{card: weight}` |
| `tiers` | one tier, `"cards"` | pools with names, `{"common": {"odds": 800, "cards": ...}, "rare": {...}}`. **The order they are written in is their rarity**, commonest first |
| `slots` | every slot by the tiers' odds | a rule per slot: `"tier"`, `{"tiers": {tier: weight}}`, `{"cards": pool}` (a pool of the slot's own) or `{"card": X}` (always that card) |
| `guarantee` | none | `{tier: n}`: at least n cards of that tier or rarer in every pack |
| `pity` | none | `{tier: n}`: the n-th pack in a row without that tier (or rarer) has one. Counted per save |
| `duplicates` | `"allow"` | `"unique_in_pack"`: no card twice in one pack, a `{"card": X}` slot's card included |
| `max_copies` | none | a card the player already holds this many of (chest and deck, and what this pack dealt, its fixed cards first) is not dealt |
| `when_nothing_left` | the shop's (`pack_shop`), `"refuse"` | with `max_copies`, when the player holds that many of every card of the pack ([Nothing left](#nothing-left)): `"refuse"`: BUY is refused and the screen says ALL OWNED, so no starchips, stock or pity are spent on a pack of empty slots; `"sell"`: sold anyway, every slot empty |
| `include_added_cards` | `true` | `false`: a card a mod added, in any pool, is left out with a note (for packs of the disc's cards only) |
| `stock` | no limit | purchases one save may make, 1 to 999999. Sold out shows SOLD OUT |
| `unlock` | open | conditions the save must meet, all of them (below) |
| `locked` | `"hidden"` | `"shown"`: a locked pack is in the list face down, as ??????, with what opens it |
| `password` | none | up to eight digits: typed on the Password screen they sell this pack (with the same confirmation). A card's password comes first. A pack with a password is not in the list unless `"listed": true` |
| `once` | `false` | a password pack a save may buy once |
| `listed` | `true`, `false` with a `password` | whether the list shows it |
| `reveal` | `"flip"` | `"flip"`: each card turned over, one at a time, ✕ for the next and □ to skip to the list; `"quick"`: turned over at twice the speed, each shown half a second and the next turned by itself (□ still skips); `"list"`: straight to the list of what came |
| `sounds` | the Password screen's | sound effect ids of the game's bank: `move` (47), `buy` (48), `refuse` (9), `reveal` (12), `back` (8). [Finding the ids](modding.md#finding-the-ids); an `audio` mod can make any of them a WAV or Ogg |

A tier:

| Key | Default | What it does |
|---|---|---|
| `odds` | 1 | its weight when a slot deals by the tiers' odds; 0 for a tier only `slots`, `guarantee` or `pity` reach |
| `cards` | | its pool, as above |
| `label` | none | what the card's line says when one of this tier turns over (`"ULTRA RARE!"`) |
| `color` | white | the label's color, the game's text colors `{f8 0A n}`: 0 white, 1 yellow, 2 blue, and so on to 15 |
| `sound` | the pack's `reveal` | the sound a card of this tier turns over with |
| `reveal` | the pack's | how a card of this tier turns over: `flip` waits for ✕ even in a quick pack (an ultra rare worth stopping for), `quick` (or `list`) turns it and goes on |

Cards are named as `decks` and `drops` name them: a name, an id, or the
`mod-id:key` identity of a card a mod added.

### Nothing left

A pack with `max_copies` has **nothing left** when the player (chest and
deck) holds `max_copies` of every card with a weight in every one of its
pools, tiers and slots' own alike, and it has no `{"card": X}` slot (a fixed
card is dealt whatever the player holds). Bought then, every slot would come
empty. By default (`"when_nothing_left": "refuse"`) such a pack is not sold:
the list shows ALL OWNED, grey, where SOLD OUT would be, and ✕ asks BUY /
QUIT with BUY grey and ALL OWNED beside the price, as it does when the
starchips fall short (□'s details say it too); nothing is paid, and the stock, the pity and the
save's counts stay as they were. `"sell"` sells it anyway, as a mod may want
(a pack bought for the count, say).

A pack with **some** cards left sells either way: its slots deal what is
left and a slot with nothing left in reach comes empty (a slot of a tier
whose cards, and the commoner tiers' below it, are all held). What came
shows only the cards dealt, and the pack counts as opened.

### A full chest

The chest keeps 250 copies of a card (or a mod's `chest_overflow` limit),
and a copy past them is lost. A pack never deals one: a card the chest has
no room for, counting what the pack dealt, is not dealt from a pool, with or
without `max_copies` (a slot with nothing left in reach comes empty, as
above), and a pack whose every card is such a card has nothing left. A fixed card (`{"card": X}`) is always dealt, so when the
chest has no room for it BUY is refused, grey, as the password shop refuses
a card the chest has no room for; nothing is paid.

### Unlock

The duelists' conditions ([more duelists](more-duelists.md)) and three of the
packs' own. All that are given must hold; nothing is stored of them, they are
read from the save and its progress each time the list opens.

| Key | Holds when |
|---|---|
| `beat` | the save has beaten this duelist (`wins` times, 1 by default) |
| `wins` | without `beat`: this many wins in all |
| `story` | the campaign's story flag is set |
| `card`, `copies` | the chest and deck hold this many copies (1 by default) |
| `starchips_spent` | the save has spent this many starchips on packs |
| `packs_opened` | the save has opened this many packs in all |
| `opened` | `{pack: n}`: the save has opened that pack n times (up to 8 packs, by identity or id) |

A condition that names something not here this run (a duelist of a mod turned
off, a pack no mod has) or is written wrong leaves the pack locked, so nothing
opens by mistake.

### The shop's rules: `pack_shop`

| Key | Default | What it does |
|---|---|---|
| `password` | `"both"` | `"both"`: the Password screen sells cards by password and packs behind △; `"packs_only"`: the screen opens on the packs, and ○ there leaves it; `"password_only"`: no △ (packs with a `password` are still sold by it) |
| `shops` | one, `main`, CARD SHOP | `[{"id", "name", "unlock"}]`: ↑/↓ on the list moves between them; a shop that is locked is skipped. Shops add up by id across mods |
| `rng` | `"game"` | `"save"`: a pack is dealt from numbers of its own, seeded by the save's duelist code, the pack and how often the save opened it, so reloading a save to buy again deals the same cards. The game's random numbers are not touched |
| `music` | 29520 | the song while the screen sells packs |
| `when_nothing_left` | `"refuse"` | what a pack that does not say does when there is nothing left in it for the player (`"refuse"` or `"sell"`, as the pack's key above); a pack's own word wins |

`pack_shop` is one mod's: the last in the load order, with a note beside it
when another mod gave one too. Its `shops` add up by id.

Not built yet, and said so when a mod asks: `campaign_shop` (a PACKS entry in
the campaign's card shop), `main_menu`, `autosave` (saving after each
purchase), `sell_added_cards` (the password shop selling mod cards by their
own passwords), a currency of the mod's own earned in duels (`cost`
`currency`), and a stock that comes back (`restock`). The design and what each
costs are in the booster-packs design notes; the keys are kept free for them.

### What the reader says

A mistake that leaves a pack unable to be dealt leaves the pack out and says
why in the Mods window: no card of it here; `count` outside 1-40; `slots` not
`count` long, or naming a tier the pack has not; a negative weight, or a
pool's weights (or the tiers' odds) adding up past 1,000,000; a price past
999999; an `id` that is not 1-63 of `[A-Za-z0-9_-]` or is another pack's of the
same mod; a tier named twice; a `guarantee` or `pity` naming no tier of the
pack, or less than 1; `cost` `cards` that is not `{card: copies}`;
`unique_in_pack` with fewer different cards than `count` (fixed cards
count), or with one card fixed in two slots; both `cards` and `tiers`; every
tier at odds 0 with a slot dealt by the odds.

Anything else is a note and the pack stays: an unknown card is left out of its
pool; an unreadable `image` shows the cover; a name past 16 letters is cut, a
description past 255 bytes too (between two letters, never inside one);
`sounds` that is not an object, or a `when_nothing_left`, `locked`, `reveal`,
`image_style` or `shop` of another kind, keeps the default; `"image_style":
"full"` without an `image` shows the cover; an unknown key gets the
likeliest meant ("did you mean"); an `unlock` naming something absent stays
locked; two packs with one password sell the first in the list's order; a
`shop` naming no shop is said. In `pack_shop`, a `password`, `rng`,
`when_nothing_left` or a shop's `where` that is not one of its words, a shop
without a proper `id`, and shops past 16 are said and left out (or the
default kept).

A key written `null` is a value of the wrong kind, not a key left out: `"price":
null` leaves the pack out as `"price": "x"` would. A whole number may be
written with a fraction of zeroes (`100.0`, `1e2`); any other fraction makes
the manifest unreadable.

At most 255 packs in all, 16 tiers a pack and 16 shops.

## How a pack is dealt

Always with **four random numbers a slot**, whatever the slot turns out to
be: two make a 30-bit roll for the tier, two a 30-bit roll for the card. A
fixed card, a pool of one card, an empty tier: still four. So a replay of the
same input (`MEMORIES_INPUT`, the headless tests) deals the same pack and
leaves the game's numbers where they would have been.

1. All the numbers are drawn first: for slot s, `a b c d`, then
   `tier_roll = a << 15 | b` and `card_roll = c << 15 | d` (each number 0-0x7FFF).
2. Each slot in turn: a fixed card is that card; a slot's own pool picks with
   `card_roll`; otherwise the tier is the slot's (`"tier"`), picked by
   `tier_roll` among the slot's weights (`{"tiers"}`) or among the tiers'
   `odds`, and the card is picked in that tier's pool with `card_roll`. A tier
   whose pool has nothing left falls to the one before it (commoner), and so
   on; with none left the slot deals nothing.
3. A pick in a pool: every card's weight as it stands (0 once
   `unique_in_pack` dealt it, 0 once the player holds `max_copies` counting
   what this pack dealt, 0 once the chest has no room for another counting
   what this pack dealt), `roll % total`, then down the pool in the order it
   was written.
4. The guarantee and the pity, rarest tier first: while the pack has fewer
   than asked of that tier or rarer, the last slot dealt by tier that has not
   got it (and was not dealt again already) is dealt again from that tier with
   its own `card_roll` — or from a rarer one when that tier has nothing left.
   A fixed card or a slot's own pool is never dealt again. The pity asks for
   one when the save's count of packs in a row without the tier reaches n - 1.

A fixed card (`{"card": X}`) counts as dealt from the start, before slot 1:
`unique_in_pack` never deals it from a pool, whatever slot it is fixed in,
and `max_copies` counts it for every slot.

`tests/pc/packs_fixture.json` and `packs_golden.txt` hold packs dealt this way;
the FM Editor's Simulate deals them the same (`tools/pc/fm_editor/packs.py`),
and both are tested against the file.

The Password screen draws no random numbers of its own each frame, and
nothing is drawn until a pack is bought.

## The screen

The Password screen's own, with nothing drawn by the port over it:

* **The digits.** The message box says `✕OK ○END △PACKS`: the game's string
  226 (or a translation's) with the triangle's icon and word after END, the
  line moved left by what it needs (on the blank line above when a
  translation's last line has no room). `password_only` leaves the string as
  it is; `packs_only` never shows it.
* **The list** (△). The digits' panel shows the pack's name, centred, in the
  panel's own 16x16 letters, 12 pixels apart (closer for a name that would
  otherwise run into the arrows, which it never does: 7 apart at 16
  letters), between the digit cursor's ◄ and ► (shown when there
  is more than one pack; ▲ and ▼ when there is more than one shop); the red
  cursor is hidden. The big card turns to the pack. The message box has the
  shop's name in blue (with more than one shop), the description's first
  lines (or how many cards), the price as the game writes a card's
  (`★x50`, `+2 CARDS` for a price in cards), `LEFT n`, `SOLD OUT` or which
  pack of how many at the right, and `✕BUY ○BACK □INFO`. When a language's
  words for them do not fit the box's twenty letters (the French, German,
  Italian and Spanish do not), `✕BUY ○BACK` is one line and `□INFO` the next,
  and the description has one line. A row of buttons is 4 pixels lower than
  the next line would be (`F8 01 10`, 16 pixels), so that their icons, 16 rows
  tall on the box's 12, clear the price's star above; so is the buttons' row
  of the reveal, of what came and of the details. A locked pack shown is face
  down, named `??????`, with LOCKED and what opens it.
* **BUY / QUIT** (✕): the game's EXCHANGE / QUIT question, word for word in
  its layout (strings 227 and 228): the name, the price, then the choice,
  BUY red and not to be chosen when the starchips, the stock, a `once` or the
  cards of the price fall short, or the pack has nothing left for the player
  (ALL OWNED beside the price, [Nothing left](#nothing-left)).
* **Paying**: the starchip count runs down as a password's does.
* **The reveal**: the big card turns over each card as it turns over a
  password's, with the tier's sound; the message box has the card's name,
  the tier's label in its color, `2/5`, NEW (gold, as card drops has it)
  when the player had no copy in the chest or the deck, and `✕NEXT □SKIP`.
* **The list of what came**: three cards to a page with NEW, ←/→ between
  pages, `✕OK`.
* **Details** (□): the whole description, cards a pack, the price and each
  card of it, each tier's chance of a slot dealt by the odds, the guarantee
  and the pity, the stock left, ALL OWNED when the pack has nothing left for
  the player, and every condition still unmet.

A pack's password typed on the digits turns the big card to the pack and
asks BUY / QUIT the same way, and afterwards the screen is the digits again.

**The pack's picture.** The big card is the game's card view, which draws the
art record of a card: its picture (102x96, 256 colors), the title plate
with its name, and the frame of its kind. A pack is shown as a card of the
first Magic card's kind, so its frame has no ATK or DEF, whose record the
load gives the pack's own picture — the PNG made the way a mod card's art is
made (`CardArt_FromImage`), with the pack's name set on the plate as a mod
card's name is (`CardArt_TitleFromName`), and drawn from the PNG itself above
the console's resolution (`TexturePack_AddMade`) — or, with no `image`, its
cover card's art with the pack's name on the plate (without a serif font to
set the name in, the cover card's own plate stays). The override is armed for
one load at a time (`Cards_OverrideArt`) and disarmed whenever the screen
opens or closes and when a state loads; HD text leaves that plate as it is
rather than setting the Magic card's name over it.

With `"image_style": "full"` the picture is the whole card instead: the PNG
as large as fits the card's 140x196, its shape kept, in the middle, with
what it leaves clear (and the PNG's own clear parts) showing the screen
behind. At the console's resolution a pixel under half opaque is clear and
the rest opaque; at 2x and 4x the PNG itself is drawn, of any size (a small
one smoothly scaled), with its own transparency.

It is made into the game's kind of texture, 8 bits a texel through 256
colors with entry 0 clear, as the title's pictures are
(`CardArt_IndexedImage`), and put in VRAM the Password screen leaves unused:
the 8-bit page at (384,256)-(511,511), its palette at (128,511) (empty in
dumps of every state of the screen: the digits, the list, BUY / QUIT,
paying, each card turning over, what came and the details). Other screens
use that VRAM (a Free Duel and a duel write row 511), so the picture is
uploaded again each time the screen opens. The card view draws it
(`func_80028B08`, asking `PackShop_Picture`) in the place of the art, the
plates and the icons, through the same turn as the card, and the frame's
front is not drawn (`DisplayObject_RenderSpriteSheet` asks
`PackShop_HidesFrame`), so the card still turns over to its back and the
picture turns in (`TexturePack_AddMadeSeeThrough` for the PNG above the
console's resolution). The card loaded under it is the first Magic card,
whose art and plate are not shown.

A state saved with the picture up has it in VRAM. Its load is read before
the state's RAM is, so the card's objects are taken at the first draw after
it, whichever screen the state was loaded from, and the picture is uploaded
again at the screen's next update so that the PNG is known above the
console's resolution. A state saved while that card turns away (to the next
pack, or to its back) shows the Magic card's frame for the rest of that half
turn after the load, since the state keeps which pack comes next, not which
one is going. Leaving the screen to the main menu, and the Free Duel after
it, draw the same as without the picture (checked). A picture that cannot be
read shows the cover, as above, with a note in the Mods window.

## The save

The memory card's save is not changed. The cards go into the chest by
`Duel_AwardCard`, as a password's card does (the disc's cards in the save, a
mod's cards beside it; `chest_overflow` applies, and the chest shows them as
new), before the first one turns over: a state saved mid-reveal, or the game
closed, never loses or doubles a card. The starchips come off the save's own
count, with the Password screen's counting down (and *Free spending*, which
takes nothing: a purchase under it adds nothing to the starchips spent on
packs, so `unlock` `starchips_spent` counts only what was paid).

What a save holds of the packs — purchases for `stock`, how often each was
opened, the pity counts, a `once` pack's password used, the starchips spent
on packs and packs opened in all — is kept beside it, in `packs/<token>.txt` in
the user directory, where the token is the save slot's (`save_slots.h`), drawn
anew each time the slot is saved:

```text
# The card packs this save bought (notes/card-packs.md).
spent 1250
opened 12
pack legend-mod:legend bought 11 opened 11 used 0 pity ultra=3
```

It is read when a slot is loaded and written when the game saves to one; the
file of the token the slot held before goes once no slot holds it. A save
without a file starts from nothing. A line for a pack no mod has this run is
kept and written back, so turning a mod off and on again loses nothing. NEW
GAME starts from nothing too.

A save state carries all of it, and where the screen was, in a chunk of its
own (`pack-shop`, versioned): the state of the list, the pack dealt and which
card is turning, the progress, and the screen's text, which the game's text
boxes point into and the load remaps to where this build keeps it. A state
without the chunk loads with the packs closed. With no pack declared there is
no chunk, so such a state is what it was.

## For a code mod

The data needs no new mod API: `packs` and `pack_shop` are manifest keys, as
`starter` and `passwords` are. The cards of a pack go through
`Duel_AwardCard`, so a code mod hears each one as `MEMORIES_EVENT_REWARD`
(before and after), as it hears a password's card. An event of its own for
each slot dealt (`MEMORIES_EVENT_PACK`, letting a mod change the card), and a
way to name a pack from code, would be the mod API's next version, and are
not built.

## Verification

`tests/pc/packs_test.c` (CTest `pc_packs`) checks every rule of the reader,
that a pack spends four numbers a slot whatever it holds, the guarantee, the
pity, `unique_in_pack` and `max_copies` (fixed cards first), the fall to a
commoner tier, `when_nothing_left`, the chest's room, the unlock conditions, the progress file
(lines of packs not here kept), `image_style` and its notes, and the deals of `packs_fixture.json` against
`packs_golden.txt` (a line ends `| nothing left` for a pack with nothing left
for the player); the FM Editor's `tests/test_packs.py` holds its reader and
Simulate to the same file and the same rules, null and all.

With the disc in `game/` and the game built, `python3 tools/pc/test_packs.py`
makes a pack mod of its own (the PNG drawn by the script), drives the game
through the control channel (`tools/pc/yfm_control.py`), opens the Password
screen (Debug > Jump to's path), gives it starchips and buys a pack, each time
from the same state loaded in place,
with △, ✕, ✕ and □, and checks that:

- the starchips drop by the price, the chest gains exactly the pack's cards,
  and they are the cards last awarded (the chest's NEW);
- the guarantee gives its rare, and the same input deals the same pack;
- a state saved while the cards turn over, resumed in a new process, ends
  with the same chest and the price paid once;
- a pack of `max_copies` 1 whose cards the save holds is refused (nothing
  paid, no card), and one that says `"when_nothing_left": "sell"` is sold,
  every slot empty;
- without the mod, △ changes nothing on the screen, and a state has no
  `pack-shop` chunk.
