#include "pc/saves/deck_menu.h"
#include "pc/platform/settings.h"
#include "pc/guest/state.h"
#include "pc/text/text.h"
#include "pc/debug/log.h"
#ifdef MEMORIES_TRANSLATED
#include "pc/guest/translated_runtime.h"
#endif
#include "types.h"
#include <assert.h>
#include <string.h>

u8 D_8009B26C, gDialog_bChoiceEnabled;
u16 D_8009B27C;
s8 gDialog_bChoiceCount, gDialog_bChoice;
static int enabled = 1, remapped;
static unsigned char text[128];
#ifdef MEMORIES_TRANSLATED
static uint32_t guest_text_base = 0xD1000000u;
uint32_t GuestRuntime_EncodePointer(void *pointer)
{
    assert(pointer == text);
    return guest_text_base;
}
#define EXPECTED_TEXT_ADDRESS guest_text_base
#else
#define EXPECTED_TEXT_ADDRESS ((uint32_t)(uintptr_t)text)
#endif

int Settings_Get(SettingId id) { assert(id == SET_DECK_SLOTS); return enabled; }
const unsigned char *Text_Own(int id)
{
    assert(id == 0x11 || id == TEXT_OWN_DECK_SLOTS);
    return NULL;
}
/* The menu's channel: 44 letters with US English, 79 with a PAL language. */
static int page_letters = 44;
int TextEntries_PageLetters(int channel) { assert(channel == 3); return page_letters; }
int Log_Wanted(LogChannel channel) { (void)channel; return 0; }
void Log_Printf(LogChannel channel, const char *format, ...) { (void)channel; (void)format; }

/* DeckMenu_ShopListing over a translation's menu: the pt-BR one's shape
 * (SALVAR, MONTAR DECK, VOLTAR AO MENU, SAIR DA LOJA) in made-up letters,
 * with spaces (glyph 0) and an added letter (F1 23). */
static void check_listings(void)
{
    static const char retail[] = "@bank dialog\n\n[0011]\n{choice 4D 9F}{f8 02 2C}SAVE\n{f8 02 14}BUILD DECK\n"
                                 "{f8 02 14}DECK SLOTS\nRETURN TO TITLE\n{f8 02 14}LEAVE SHOP\n"
                                 "{choose 80 0 0 0 0 0}\n";
    static const unsigned char menu[] = {
        0xFB, 0x4C, 0x8F, 0xF8, 0x02, 0x24, 1, 2, 3, 4, 5, 6, 0xFE,     /* 6 letters */
        0xF8, 0x02, 0x10, 1, 2, 3, 4, 5, 6, 0, 7, 8, 9, 10, 0xFE,       /* 11 */
        1, 2, 3, 4, 5, 6, 0, 7, 8, 0, 9, 10, 0xF1, 0x23, 11, 0xFE,     /* 15 */
        0xF8, 0x02, 0x0C, 1, 2, 3, 4, 0, 5, 6, 0, 7, 8, 9, 10, 0xFE,    /* 12 */
        0xFB, 0x80, 0, 0, 0, 0, 0, 0, 0, 0, 0xFF};
    static const unsigned char label[] = {0x2A, 0x1F, 0, 0xF1, 0x23, 0xFF}; /* 3 letters and a space */
    /* 6 more: the menu's 38 and these are the box's 44; 7 are too many. */
    static const unsigned char fits[] = {1, 2, 3, 4, 5, 6, 0xFF}, too_long[] = {1, 2, 3, 4, 5, 6, 7, 0xFF};
    static const unsigned char coded[] = {0xFB, 0x4C, 0x8F, 0xF8, 0x17, 0, 0, 0xFE, 0xFF};
    static const unsigned char two_lines[] = {0x2A, 0xFE, 0x2A, 0xFF};
    char out[2400];
    assert(DeckMenu_ShopListing(out, sizeof(out), NULL, NULL) && !strcmp(out, retail));
    /* The translation's lines as {g}, the entry under the second, centred
     * on the widest line's middle (0x24 + 6 * 4 = 60): 60 - 4 * 4 = 0x2C. */
    assert(DeckMenu_ShopListing(out, sizeof(out), menu, label));
    assert(strstr(out, "[0011]\n{choice 4D 9F}{f8 02 24}{g 1}{g 2}{g 3}{g 4}{g 5}{g 6}\n"));
    assert(strstr(out, "{g A}\n{f8 02 2C}{g 2A}{g 1F}{g 0}{g 123}\n{g 1}"));
    assert(strstr(out, "{g 123}{g B}\n{f8 02 0C}{g 1}"));
    assert(strstr(out, "{g A}\n{choose 80 0 0 0 0 0}\n"));
    /* The box's letters: the English entry (9) does not fit over this
     * menu (38); one of 6 does. */
    assert(DeckMenu_ShopListing(out, sizeof(out), menu, fits));
    assert(!DeckMenu_ShopListing(out, sizeof(out), menu, too_long));
    assert(!DeckMenu_ShopListing(out, sizeof(out), menu, NULL));
    /* The translation's entry over retail's menu. */
    assert(DeckMenu_ShopListing(out, sizeof(out), NULL, label) && strstr(out, "BUILD DECK\n{f8 02 2C}{g 2A}"));
    /* A menu with codes a line has no use for, an entry of two lines, or
     * no room: no entry. */
    assert(!DeckMenu_ShopListing(out, sizeof(out), coded, NULL));
    assert(!DeckMenu_ShopListing(out, sizeof(out), NULL, two_lines));
    assert(!DeckMenu_ShopListing(out, 64, NULL, NULL));
    /* With a PAL language the channel has the PAL game's room: the English
     * entry over this menu (47), and 41 letters more (79). */
    page_letters = 79;
    assert(DeckMenu_ShopListing(out, sizeof(out), menu, NULL) && strstr(out, "{g A}\n{f8 02 14}DECK SLOTS\n{g 1}"));
    assert(DeckMenu_ShopListing(out, sizeof(out), menu, too_long));
    page_letters = 44;
}
const unsigned char *Text_CompileOwn(const char *listing, int id, size_t *size)
{
    assert(id == 0x11 && strstr(listing, "DECK SLOTS"));
    *size = sizeof(text);
    return text;
}
struct MemoriesState { int loading, present; unsigned char data[12]; };
int Memories_StateLoading(const MemoriesState *state) { return state->loading; }
int Memories_StateChunk(MemoriesState *state, const char *tag, const MemoriesStateField *fields, size_t count)
{
    size_t i, at = 0;
    assert(!strcmp(tag, "deck-shop") && count == 3);
    if (state->loading && !state->present) return 0;
    for (i = 0; i < count; i++) {
        assert(at + fields[i].size <= sizeof(state->data));
        if (state->loading) memcpy(fields[i].data, state->data + at, fields[i].size);
        else memcpy(state->data + at, fields[i].data, fields[i].size);
        at += fields[i].size;
    }
    state->present = 1;
    return state->loading;
}
void Memories_StateRemapRange(MemoriesState *state, uint32_t from, uint32_t to, uint32_t size)
{
#ifdef MEMORIES_TRANSLATED
    if (!remapped) assert(from == 0xD1000000u && to == 0xD2000000u);
    else assert(from == 0xD2000000u && to == 0xD2000000u);
#else
    assert(from == EXPECTED_TEXT_ADDRESS && to == EXPECTED_TEXT_ADDRESS);
#endif
    assert(state->loading && from && to == EXPECTED_TEXT_ADDRESS && size == sizeof(text));
    remapped++;
}

int main(void)
{
    MemoriesState five = {0}, four = {0}, old = {1, 0, {0}};
    D_8009B26C = 2;
    D_8009B27C = 0xc00d;
    assert(DeckMenu_ShopMenu());
    assert(DeckMenu_Text(0x11) == text);
    assert(DeckMenu_ShopChoice(2) == DECK_MENU_SHOP_SLOTS);
    assert(DeckMenu_ShopChoice(3) == 2 && DeckMenu_ShopChoice(4) == 3);
    gDialog_bChoiceCount = 4;
    gDialog_bChoiceEnabled = 15;
    gDialog_bChoice = 2;
    DeckMenu_ShopRestore();
    assert(gDialog_bChoiceCount == 5 && gDialog_bChoice == 3 && gDialog_bChoiceEnabled == 31);
    gDialog_bChoiceEnabled = 3; /* Return to Title's Yes/No prompt */
    gDialog_bChoice = 2;
    DeckMenu_ShopRestore();
    assert(gDialog_bChoice == 3 && gDialog_bChoiceEnabled == 31);
    DeckMenu_ShopState(&five);
#ifdef MEMORIES_TRANSLATED
    {
        uint32_t saved_base;
        memcpy(&saved_base, five.data + sizeof(int), sizeof(saved_base));
        assert(saved_base == 0xD1000000u); /* save the guest token, not the host pointer's low bits */
        guest_text_base = 0xD2000000u;     /* a fresh guest-visible allocation after restart */
    }
#endif

    enabled = 0;
    assert(!DeckMenu_ShopMenu());
    DeckMenu_ShopState(&four);
    five.loading = 1;
    DeckMenu_ShopState(&five);
    /* The saved menu controls numbering, regardless of the current setting
     * or the most recently visited shop. */
    assert(DeckMenu_ShopChoice(2) == DECK_MENU_SHOP_SLOTS && remapped == 1);
    four.loading = 1;
    DeckMenu_ShopState(&four);
    assert(DeckMenu_ShopChoice(2) == 2 && DeckMenu_Text(0x11) == 0);
    enabled = 1;
    assert(DeckMenu_ShopMenu());
    DeckMenu_ShopState(&old);
    assert(DeckMenu_ShopChoice(2) == 2);
    check_listings();
    return 0;
}
