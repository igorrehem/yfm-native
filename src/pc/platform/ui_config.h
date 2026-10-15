#ifndef MEMORIES_PC_PLATFORM_UI_CONFIG_H
#define MEMORIES_PC_PLATFORM_UI_CONFIG_H
/* The mods' "ui" key as read (ui_config.c): the duel's pictures -- the two
 * halves of the life-point panel, the FIELD box, the card bar and the
 * cursors -- moved, sized, colored, hidden or drawn from a PNG of the
 * mod's own; pc/cards/duel_ui.h draws them so. Places are in the game's
 * 320 x 240, colors 0xRRGGBB. Only the reading is here, so
 * tests/pc/ui_config_test.c checks it at the host's own width. */
#include <stdint.h>

struct JsonValue;

/* The elements, in "ui"."duel" order (UiConfig_ElementNames). */
enum {
    UI_LP_OPPONENT,   /* the panel's top half: the opponent's LP, COM, their deck count */
    UI_LP_PLAYER,     /* its bottom half: YOU, the player's LP and deck count */
    UI_FIELD,         /* the FIELD box, the terrain's name */
    UI_CARD_BAR,      /* the strip under the hand: the card's name, ATK/DEF, stars */
    UI_HAND_CURSOR,   /* the red arrow under the hand */
    UI_FIELD_CURSOR,  /* the hand pointing at a zone */
    UI_ELEMENTS
};
enum { UI_PATH = 1024, UI_LABEL = 16, UI_SCALE_MIN = 25, UI_SCALE_MAX = 400 };
extern const char *const UiConfig_ElementNames[UI_ELEMENTS];

typedef struct {
    char file[UI_PATH];         /* the PNG, "" for the game's own picture */
    char mod[64];
    int width, height;          /* its size in the game's pixels, 0 the element's */
} UiImage;

typedef struct {
    int set;                    /* a mod changed it: drawn by duel_ui.c */
    char mod[64];               /* the last mod that did */
    int x, y;                   /* moved by, in the game's pixels */
    int scale;                  /* percent of its size, about its middle (100 as it is) */
    uint32_t tint;              /* its colors multiplied, 0xFFFFFF as they are */
    uint32_t digits;            /* the LP and deck digits' colors (the LP halves) */
    int hidden;
    UiImage image;
    char label[UI_LABEL];       /* the LP halves: words in place of COM or YOU */
} UiElement;

/* The card bar's parts, in "ui"."duel"."card_bar" (UiConfig_PartNames):
 * the words, numbers and icons the game writes over the bar as one text
 * (func_80023144), each moved within the bar, colored or hidden as it is
 * drawn (duel_ui.c). Places are from where the game puts them, in the
 * game's pixels. */
enum {
    UI_PART_NAME,     /* the card's name */
    UI_PART_ATK,      /* the sword and the ATK digits */
    UI_PART_DEF,      /* the shield and the DEF digits */
    UI_PART_TYPE,     /* the type's icon (Dragon, Spellcaster, Magic...) */
    UI_PART_STARS,    /* the guardian stars' icons (on the field, the active one) */
    UI_PART_KIND,     /* a magic, trap, equip or ritual card's word */
    UI_PARTS
};
/* The bar's text box (its 16, 210 under the hand) is where a part is
 * placed from: a part stays on the bar's dark panel, the same under the
 * hand and on the bar's higher look, from x -2 to 290 and y -2 to 18 of the
 * box (the letters' cells are dark: off the panel they would show); how
 * far the name's letters may be spread or drawn together (spread by 2 the
 * longest name just fits). */
enum { UI_BAR_LEFT = -2, UI_BAR_RIGHT = 290, UI_BAR_TOP = -2, UI_BAR_BOTTOM = 18, UI_SPACING_MIN = -3,
       UI_SPACING_MAX = 2 };
extern const char *const UiConfig_PartNames[UI_PARTS];

typedef struct {
    int set;                    /* a mod changed it */
    char mod[64];
    int x, y;                   /* moved by, kept on the bar (UiConfig_PartRange) */
    uint32_t tint;              /* its colors multiplied, 0xFFFFFF as they are */
    int hidden;
    int spacing;                /* the name: pixels more (or fewer) between its letters */
} UiPart;

typedef struct {
    UiElement element[UI_ELEMENTS];
    UiPart part[UI_PARTS];
    int any;                    /* some element is set */
    int parts;                  /* some part of the card bar is changed */
} UiConfig;

/* Where a part is as the game draws it, in the bar's text box (x, y, w,
 * h; the name at its longest, 28 letters, spread by `spacing`), and how far
 * it may be moved and still be on the bar. */
void UiConfig_PartHome(int part, int spacing, int *x, int *y, int *w, int *h);
void UiConfig_PartRange(int part, int spacing, int *x0, int *x1, int *y0, int *y1);

/* Elements the game slides off the screen sideways (the LP halves, the
 * FIELD box) are moved up or down only and sized no more than leaves the
 * screen with the game's (ui_config.c). How far an element drawn at
 * `scale` (its own pieces, or a picture of the mod's own with its "width"
 * and "height", 0 for the element's) reaches from its middle; the most
 * size at which it still leaves the screen (UI_SCALE_MAX for one that does
 * not slide, 100 for one that cannot be sized). */
int UiConfig_Reach(int which, int scale, int picture, int width, int height);
int UiConfig_ScaleMax(int which, int picture, int width, int height);
/* The retail duel, then each applied mod's "ui" over it, a later mod's
 * value winning key by key. */
const UiConfig *UiConfig_Load(void);
const UiConfig *UiConfig_Get(void);
/* The pieces of UiConfig_Load, for tests: back to retail, and one
 * manifest's "ui" over what there is (`directory` names its "image"s). */
void UiConfig_Reset(void);
void UiConfig_Read(const char *mod, const char *directory, const struct JsonValue *manifest);
#endif
