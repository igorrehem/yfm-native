/* The campaign shop's added DECK SLOTS entry (deck_menu.h). */
#include "deck_menu.h"
#include "pc/platform/settings.h"
#include "pc/text/text.h"
#include "pc/text/entry_layout.h"
#include "pc/guest/state.h"
#ifdef MEMORIES_TRANSLATED
#include "pc/guest/translated_runtime.h"
#endif
#include "pc/debug/log.h"
#include "types.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

extern u8 D_8009B26C;
extern u16 D_8009B27C;
extern u8 gDialog_bChoiceEnabled;
extern s8 gDialog_bChoiceCount, gDialog_bChoice;
#define MODE_CAMPAIGN 2
#define SCRIPT_COMMAND_SHOP 13

/* The card shop's menu, string 0x11, with DECK SLOTS under BUILD DECK: the
 * retail listing's lines (tools/pc/text_listing.py) and one more, as wide as
 * BUILD DECK and indented as it is. {choice} offers five and {choose} jumps
 * as retail's do. The game keeps four entries' worth of enabled bits
 * (Text_HandleChoiceCommand), so DeckMenu_ShopRestore sets the fifth. */
#define SHOP_MENU_TEXT 0x11
#define SHOP_MENU_SLOTS 2
static const char shop_listing[] = "@bank dialog\n"
                                   "\n"
                                   "[0011]\n"
                                   "{choice 4D 9F}{f8 02 2C}SAVE\n"
                                   "{f8 02 14}BUILD DECK\n"
                                   "{f8 02 14}DECK SLOTS\n"
                                   "RETURN TO TITLE\n"
                                   "{f8 02 14}LEAVE SHOP\n"
                                   "{choose 80 0 0 0 0 0}\n";
static size_t shop_text_size;

/* --- the menu over a translation's ------------------------------------ */

/* The menu is text channel 3's, whose slice of the game's glyph entries
 * holds 45: 44 letters (a space is none) and the end; with a PAL language
 * 80, as on the PAL console (entry_layout.h). Retail's with DECK SLOTS has
 * exactly 44; past them the last line is cut short. */
#define SHOP_MENU_CHANNEL 3

/* A menu line as the listing writes it, where its middle is, and its
 * letters. */
typedef struct {
    char source[400];
    int indent, width, letters;
} ShopLine;

static void append(ShopLine *line, const char *text)
{
    size_t used = strlen(line->source);
    snprintf(line->source + used, sizeof(line->source) - used, "%s", text);
}

/* The letters and steps of compiled text up to a line break or the end, into
 * `line`; the text after them, or NULL for a code a menu line has no use for
 * (the DECK SLOTS entry's own string takes letters and spaces only). */
static const unsigned char *shop_line(const unsigned char *text, ShopLine *line, int letters_only)
{
    char code[24];
    int start = 1;
    memset(line, 0, sizeof(*line));
    while (*text != 0xFE && *text != 0xFF) {
        if (*text == 0xF8 && !letters_only && (text[1] == 0x02 || text[1] == 0x0A)) {
            snprintf(code, sizeof(code), "{f8 %02X %02X}", text[1], text[2]);
            if (text[1] == 0x02 && start) line->indent += text[2];
            else if (text[1] == 0x02) line->width += text[2];
            text += 3;
        } else if (*text >= 0xF6 || (*text >= 0xF0 && text[1] == 0xFF)) {
            return NULL;
        } else {
            int glyph = *text >= 0xF0 ? ((text[0] - 0xF0) << 8) | text[1] : *text;
            text += *text >= 0xF0 ? 2 : 1;
            snprintf(code, sizeof(code), "{g %X}", glyph);
            line->width += 8;
            line->letters += glyph != 0;
            start = 0;
        }
        if (strlen(line->source) + strlen(code) >= sizeof(line->source) - 16) return NULL;
        append(line, code);
    }
    return text;
}

int DeckMenu_ShopListing(char *out, size_t size, const unsigned char *menu, const unsigned char *label)
{
    ShopLine lines[4], added;
    int control, mask = -1, count = 0, middle = 0, i, at, letters, room = TextEntries_PageLetters(SHOP_MENU_CHANNEL);
    char head[32];
    /* The DECK SLOTS entry's words. */
    memset(&added, 0, sizeof(added));
    if (label) {
        const unsigned char *end = shop_line(label, &added, 1);
        if (!end || *end != 0xFF || !added.width) return 0;
    } else {
        snprintf(added.source, sizeof(added.source), "DECK SLOTS");
        added.width = 10 * 8;
        added.letters = 9;
    }
    /* The shop's menu, retail's or a translation's: {choice} for four
     * entries, then four lines, then {choose}. */
    if (!menu) {
        static const char *const retail[4] = {"{f8 02 2C}SAVE", "{f8 02 14}BUILD DECK", "RETURN TO TITLE",
                                              "{f8 02 14}LEAVE SHOP"};
        static const int indents[4] = {0x2C, 0x14, 0, 0x14}, widths[4] = {4, 10, 15, 10}, counts[4] = {4, 9, 13, 9};
        control = 0x4C;
        mask = 0x8F;
        for (i = 0; i < 4; i++) {
            memset(&lines[i], 0, sizeof(lines[i]));
            snprintf(lines[i].source, sizeof(lines[i].source), "%s", retail[i]);
            lines[i].indent = indents[i];
            lines[i].width = widths[i] * 8;
            lines[i].letters = counts[i];
        }
        count = 4;
    } else {
        if (menu[0] != 0xFB || (menu[1] & 0x87) != 0x04) return 0;
        control = menu[1];
        menu += 2;
        if (control & 0x08) mask = *menu++;
        while (count < 4) {
            menu = shop_line(menu, &lines[count], 0);
            if (!menu || *menu != 0xFE) return 0;
            menu++;
            count++;
        }
        if (menu[0] != 0xFB || menu[1] != 0x80) return 0;
    }
    /* Centred as the others are: on the widest line's middle. */
    letters = added.letters;
    for (i = 0; i < count; i++) {
        int m = lines[i].indent + lines[i].width / 2;
        if (m > middle) middle = m;
        letters += lines[i].letters;
    }
    if (letters > room) {
        LOG(LOG_MODS, "text: the card shop's menu with DECK SLOTS (%04X) would have %d letters; its box shows %d, "
                      "so it keeps its four entries", TEXT_OWN_DECK_SLOTS, letters, room);
        return 0;
    }
    at = middle - added.width / 2;
    if (at > 0) {
        size_t length;
        snprintf(head, sizeof(head), "{f8 02 %02X}", at > 0xFF ? 0xFF : at);
        length = strlen(head);
        memmove(added.source + length, added.source, strlen(added.source) + 1);
        memcpy(added.source, head, length);
    }
    /* One entry more, enabled, under BUILD DECK (the mask's third bit). */
    if (mask >= 0) {
        mask = (mask & 0x03) | 0x04 | ((mask & 0x0C) << 1) | (mask & 0xE0);
        snprintf(head, sizeof(head), "{choice %02X %02X}", control + 1, mask);
    } else {
        snprintf(head, sizeof(head), "{choice %02X}", control + 1);
    }
    i = snprintf(out, size, "@bank dialog\n\n[0011]\n%s%s\n%s\n%s\n%s\n%s\n{choose 80 0 0 0 0 0}\n", head,
                 lines[0].source, lines[1].source, added.source, lines[2].source, lines[3].source);
    return i > 0 && (size_t)i < size;
}
static int shop_extra; /* the shop's menu on screen has DECK SLOTS */

static int in_shop(void)
{
    return (D_8009B26C & 0x1F) == MODE_CAMPAIGN && (D_8009B27C & 0x1F) == SCRIPT_COMMAND_SHOP;
}

static const unsigned char *shop_text(void)
{
    static const unsigned char *text;
    static int tried;
    if (!tried) {
        const unsigned char *menu = Text_Own(SHOP_MENU_TEXT), *label = Text_Own(TEXT_OWN_DECK_SLOTS);
        static char listing[2400];
        tried = 1;
        if (!menu && !label) {
            text = Text_CompileOwn(shop_listing, SHOP_MENU_TEXT, &shop_text_size);
        } else if (DeckMenu_ShopListing(listing, sizeof(listing), menu, label)) {
            /* A translation's menu or DECK SLOTS (text.h), with the entry. */
            text = Text_CompileOwn(listing, SHOP_MENU_TEXT, &shop_text_size);
        } else {
            LOG(LOG_MODS, "text: the card shop's menu (0011) or DECK SLOTS (%04X) of a translation is not a "
                          "four-line menu of plain words, or too long; the shop has no DECK SLOTS",
                TEXT_OWN_DECK_SLOTS);
            return NULL;
        }
        if (!text) fprintf(stderr, "memories-pc: the card shop's menu with DECK SLOTS did not compile\n");
    }
    return text;
}

static uintptr_t shop_text_address(const unsigned char *pointer)
{
#ifdef MEMORIES_TRANSLATED
    return GuestRuntime_EncodePointer((void *)pointer);
#else
    return (uintptr_t)pointer;
#endif
}

/* Restore this before the game image: its text streams contain pointers
 * into the compiled listing, whose heap address changes between sessions. */
void DeckMenu_ShopState(MemoriesState *state)
{
    uint32_t base = shop_text_size ? (uint32_t)shop_text_address(shop_text()) : 0;
    uint32_t size = (uint32_t)shop_text_size;
    MemoriesStateField fields[] = {{&shop_extra, sizeof(shop_extra)}, {&base, sizeof(base)}, {&size, sizeof(size)}};
    if (Memories_StateLoading(state)) shop_extra = 0; /* older states had four entries */
    if (Memories_StateChunk(state, "deck-shop", fields, 3) && base && size) {
        const unsigned char *text = shop_text();
        if (text && size == shop_text_size) {
            Memories_StateRemapRange(state, base, (uint32_t)shop_text_address(text), size);
        }
    }
}

int DeckMenu_ShopMenu(void)
{
    shop_extra = Settings_Get(SET_DECK_SLOTS) && shop_text();
    return shop_extra;
}

const unsigned char *DeckMenu_Text(int id)
{
    return id == SHOP_MENU_TEXT && shop_extra && in_shop() ? shop_text() : NULL;
}

int DeckMenu_ShopChoice(int choice)
{
    if (!shop_extra) return choice;
    if (choice == SHOP_MENU_SLOTS) return DECK_MENU_SHOP_SLOTS;
    return choice > SHOP_MENU_SLOTS ? choice - 1 : choice;
}

void DeckMenu_ShopRestore(void)
{
    if (!shop_extra) return;
    /* Nested memory-card and title prompts overwrite the global enabled
     * mask. All five entries in this menu are enabled, as in its listing. */
    gDialog_bChoiceCount = 5;
    if (gDialog_bChoice >= SHOP_MENU_SLOTS) gDialog_bChoice++;
    gDialog_bChoiceEnabled = 0x1F;
}

