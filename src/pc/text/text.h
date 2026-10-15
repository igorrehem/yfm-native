#ifndef MEMORIES_PC_TEXT_H
#define MEMORIES_PC_TEXT_H
#include <stddef.h>
/* Translations: the game's text as mods rewrite it (notes/translation.md).
 *
 * A mod's "text" names listings (tools/pc/text_listing.py writes the
 * retail one) whose strings stand in for the game's, by string id: the
 * dialogue and menus, the card descriptions, and the card, type and
 * duelist names. "font" names font files for letters the game has none of.
 * The game's own code asks Text_Resolve wherever it turns a string id into
 * text, and Text_Retarget wherever a text jumps. */

/* Read and compile every applied mod's text and fonts; once, at startup,
 * before the cards, whose names may use the fonts' letters. */
void Text_Build(void);

/* Once the cards are built: if a translation renames cards, the
 * alphabetical order the Library and Build Deck sort by is the new names'. */
void Text_SortCards(void);

/* The text for string `id`: a mod's, else `retail`. */
const unsigned char *Text_Resolve(int id, const unsigned char *retail);

/* A menu with choices is laid out in one go: func_80039794 steps its text
 * with no frame in between until the last choice line is down. A line
 * wider than the box wraps by itself, and if that row pushes the menu past
 * the box's height first, the text waits for a button that nothing in that
 * loop reads, and the game stops (the console's too; notes/translation.md).
 * Whether the glyph at `x`, `y` of string `id`'s menu, with `lines_left`
 * choice lines still to come, is dropped instead: only where the wrap would
 * stop the game, so a line cut at the box's edge is all that changes. */
int Text_CutsMenuGlyph(int id, int x, int width, int y, int line_height, int height, int lines_left);

/* Whether an applied mod's text rewrites string `id`. */
int Text_Overridden(int id);
/* The port's own strings, which it draws in the game's letters inside the
 * game's picture: ids no retail string has, in the dialogue bank, which a
 * translation may define as it does the game's (notes/translation.md lists
 * them). `%d` stands for a number the port puts in. */
#define TEXT_OWN_FIRST 0xFE00
#define TEXT_OWN_LAST 0xFEFF
enum {
    TEXT_OWN_NEW = 0xFE00,          /* card drops: a card the player had none of */
    TEXT_OWN_MORE_CARD = 0xFE01,    /* card drops: the heading, one card past the first */
    TEXT_OWN_MORE_CARDS = 0xFE02,   /* card drops: the heading, more */
    TEXT_OWN_PAGE_OF = 0xFE03,      /* card drops: which page of how many */
    TEXT_OWN_DECK_SLOTS = 0xFE10,   /* the card shop's added menu entry */
    TEXT_OWN_FREE_DUEL_PAGE = 0xFE11, /* the Free Duel grid's page line */
    /* The card packs on the Password screen (pc/cards/pack_shop.h). */
    TEXT_OWN_PACK_PACKS = 0xFE20,   /* after "OK END": the triangle's word */
    TEXT_OWN_PACK_BUY = 0xFE21,
    TEXT_OWN_PACK_QUIT = 0xFE22,
    TEXT_OWN_PACK_BACK = 0xFE23,
    TEXT_OWN_PACK_INFO = 0xFE24,
    TEXT_OWN_PACK_NEXT = 0xFE25,
    TEXT_OWN_PACK_SKIP = 0xFE26,
    TEXT_OWN_PACK_OK = 0xFE27,
    TEXT_OWN_PACK_END = 0xFE28,
    TEXT_OWN_PACK_SOLD_OUT = 0xFE29,
    TEXT_OWN_PACK_LEFT = 0xFE2A,    /* purchases left of a pack's stock */
    TEXT_OWN_PACK_CARDS = 0xFE2B,   /* cards a pack deals, or a price takes */
    TEXT_OWN_PACK_LOCKED = 0xFE2C,
    TEXT_OWN_PACK_BEAT = 0xFE2D,    /* what opens a locked pack: %s a duelist */
    TEXT_OWN_PACK_BEAT_TIMES = 0xFE2E,
    TEXT_OWN_PACK_WINS = 0xFE2F,
    TEXT_OWN_PACK_STORY = 0xFE30,
    TEXT_OWN_PACK_HOLD = 0xFE31,    /* %s a card */
    TEXT_OWN_PACK_HOLD_COPIES = 0xFE32,
    TEXT_OWN_PACK_SPEND = 0xFE33,
    TEXT_OWN_PACK_OPEN_MORE = 0xFE34,
    TEXT_OWN_PACK_OPEN_PACK = 0xFE35, /* %s a pack */
    TEXT_OWN_PACK_AT_LEAST = 0xFE36,  /* the details: a guarantee, %s a tier */
    TEXT_OWN_PACK_PITY = 0xFE37,
    TEXT_OWN_PACK_CARD = 0xFE38,    /* one card */
    TEXT_OWN_PACK_ALL_OWNED = 0xFE39, /* why BUY is refused: every card held "max_copies" times */
    TEXT_OWN_OPPONENT = 0xFE40,     /* + duelist id (1-39, FE41-FE67): the name in place of COM */
    /* The tower's screen (pc/tower/tower.h). */
    TEXT_OWN_TOWER_FLOOR = 0xFE70,  /* FLOOR %d OF %d: %s (the opponent) */
    TEXT_OWN_TOWER_DUEL = 0xFE71,
    TEXT_OWN_TOWER_LEAVE = 0xFE72,
    TEXT_OWN_TOWER_NO_FUSIONS = 0xFE73,
    TEXT_OWN_TOWER_NO_EQUIPS = 0xFE74,
    TEXT_OWN_TOWER_LIFE_POINTS = 0xFE75, /* LP YOU %d COM %d: the player's, the opponent's */
    TEXT_OWN_TOWER_CLEARED = 0xFE76, /* CLEARED x%d: times the tower was won */
    TEXT_OWN_TOWER_FLOOR_WON = 0xFE77,
    TEXT_OWN_TOWER_STARCHIPS = 0xFE78,
    TEXT_OWN_TOWER_UNLOCKED = 0xFE79, /* %s UNLOCKED: a duelist */
    TEXT_OWN_TOWER_CHECKPOINT = 0xFE7A,
    TEXT_OWN_TOWER_COMPLETE = 0xFE7B,
    TEXT_OWN_TOWER_LOST = 0xFE7C,   /* YOU LOST. BACK TO FLOOR %d. */
    TEXT_OWN_TOWER_SAVE = 0xFE7D,
    TEXT_OWN_TOWER_YES = 0xFE7E,
    TEXT_OWN_TOWER_NO = 0xFE7F
};
/* Ids above the block, which the port composes rather than a translation
 * writing them: FF00-FF57 the name of a duelist a mod added, one each
 * (free_duel/duelists.h), FFF0-FFF2 the card packs' name, message and
 * question (cards/pack_shop.h), FFF8 the tower's box (tower/tower.h), and FFFD-FFFF one line apiece for the Free Duel
 * grid's page, the Password screen's label and the results screen's added
 * pages (free_duel/page_box.h, cards/passwords.h, cards/drops.h). */
/* The compiled text an applied mod gives string `id` (glyph codes and
 * codes, ending in {end}), or NULL: for the port's own strings, and for a
 * retail string the port adds to. */
const unsigned char *Text_Own(int id);
/* The name in place of COM (View > Opponent's name for COM) for a duelist
 * (1-39), in Latin-1: a translation's TEXT_OWN_OPPONENT + id; else its name
 * for the duelist in the names bank (0x8328 + id) when it differs from the
 * English, shortened as Tables_ShortenName does; else the English
 * (Tables_DuelistShortName). NULL for no opponent. */
const char *Text_OpponentName(int duelist);

/* String `id` of a listing the port writes itself (a menu it adds an entry
 * to), compiled as a mod's text is, so that its jumps land (Text_Retarget);
 * it stands in for nothing by itself. NULL if it does not compile. */
const unsigned char *Text_CompileOwn(const char *listing, int id, size_t *size);

/* Where a jump from the stream at `cursor` to `target` lands: into the
 * translation `cursor` is in, by the translation's own targets, or, for the
 * game's own text, `target` in the cursor's 64 KB bank. */
unsigned char *Text_Retarget(unsigned char *cursor, unsigned target);

/* Where the text compiled at startup lies, which the game's text boxes
 * point into and a save state keeps (state.c): the fixed region's address
 * (0 when the text had to stay on the heap), how many of its bytes the
 * startup text takes (on the heap, how many it has), and a CRC-32 of that
 * text unit by unit. All 0 with no text compiled. Text_Build fixes it; the
 * shop's menu, compiled later from that text, is not in it. */
typedef struct {
    unsigned base, used, crc;
} TextLayout;
TextLayout Text_Layout(void);

#endif
