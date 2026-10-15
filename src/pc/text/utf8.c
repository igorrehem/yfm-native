/* UTF-8, for the text a mod writes (glyphs.h). Apart from glyphs.c so the
 * listing compiler can be tested without the renderer. */
#include "glyphs.h"
#include <stddef.h>

uint32_t Glyphs_NextCharacter(const char **text)
{
    const unsigned char *at = (const unsigned char *)*text;
    uint32_t character;
    int more, i;
    if (*at < 0x80) { *text += 1; return *at; }
    if ((*at & 0xE0) == 0xC0) { character = *at & 0x1F; more = 1; }
    else if ((*at & 0xF0) == 0xE0) { character = *at & 0x0F; more = 2; }
    else if ((*at & 0xF8) == 0xF0) { character = *at & 0x07; more = 3; }
    else { *text += 1; return GLYPHS_NOT_UTF8; }
    for (i = 1; i <= more; i++) {
        if ((at[i] & 0xC0) != 0x80) { *text += i; return GLYPHS_NOT_UTF8; }
        character = (character << 6) | (at[i] & 0x3F);
    }
    *text += more + 1;
    /* Too long a spelling, a surrogate or past Unicode: no character. */
    if (character < (more == 1 ? 0x80u : more == 2 ? 0x800u : 0x10000u) ||
        (character >= 0xD800 && character <= 0xDFFF) || character > 0x10FFFF)
        return GLYPHS_NOT_UTF8;
    return character;
}

/* --- NFC ------------------------------------------------------------------- */

#include "compose.inc"

static int mark_class(uint32_t mark)
{
    size_t i;
    for (i = 0; i < sizeof(mark_classes) / sizeof(mark_classes[0]); i++) {
        if (mark_classes[i].mark == mark) return mark_classes[i].order;
    }
    return 230;   /* most marks above are; one the table lacks composes with nothing */
}

static uint32_t composed(uint32_t letter, uint32_t mark)
{
    size_t low = 0, high = sizeof(compositions) / sizeof(compositions[0]);
    while (low < high) {
        size_t middle = (low + high) / 2;
        uint32_t key = compositions[middle].letter, key_mark = compositions[middle].mark;
        if (key == letter && key_mark == mark) return compositions[middle].composed;
        if (key < letter || (key == letter && key_mark < mark)) low = middle + 1;
        else high = middle;
    }
    return 0;
}

uint32_t Glyphs_NextComposed(const char **text, uint32_t left[GLYPHS_MARKS_MAX], int *left_count)
{
    uint32_t marks[GLYPHS_MARKS_MAX], letter = Glyphs_NextCharacter(text);
    int count = 0, i, j, blocking = 0;
    *left_count = 0;
    if (letter == GLYPHS_NOT_UTF8 || (letter >= 0x300 && letter <= 0x36F)) return letter;
    /* The combining marks after it, in their canonical order (a stable
     * sort by class: dot below before ^, whichever was typed first). */
    while (count < GLYPHS_MARKS_MAX) {
        const char *at = *text;
        uint32_t mark = Glyphs_NextCharacter(&at);
        if (mark < 0x300 || mark > 0x36F) break;
        *text = at;
        for (i = count; i > 0 && mark_class(marks[i - 1]) > mark_class(mark); i--) marks[i] = marks[i - 1];
        marks[i] = mark;
        count++;
    }
    /* Each onto the letter unless a mark left over before it has its
     * class (or it composes with nothing): e + ^ + ´ is ế, a + ̣ + ˘ is ặ. */
    for (i = 0; i < count; i++) {
        uint32_t with = blocking < mark_class(marks[i]) ? composed(letter, marks[i]) : 0;
        if (with) {
            letter = with;
            continue;
        }
        j = mark_class(marks[i]);
        if (j > blocking) blocking = j;
        left[(*left_count)++] = marks[i];
    }
    return letter;
}
