/* Tags in a card's notes (card_notes.h). */
#include "card_notes.h"
#include <ctype.h>
#include <string.h>

static int blank(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }

/* [*start, *end) without the blanks around it. */
static void trim(const char **start, const char **end)
{
    while (*start < *end && blank(**start)) (*start)++;
    while (*end > *start && blank((*end)[-1])) (*end)--;
}

static int same_name(const char *name, size_t length, const char *key)
{
    size_t i;
    for (i = 0; i < length; i++) {
        if (!key[i] || tolower((unsigned char)name[i]) != tolower((unsigned char)key[i])) return 0;
    }
    return !key[length];
}

int CardNotes_Tag(const char *notes, const char *key, char *out, size_t size)
{
    const char *found = NULL, *found_end = NULL, *p;
    size_t length;
    if (out && size) *out = '\0';
    if (!notes || !key) return -1;
    for (p = strchr(notes, '<'); p; p = strchr(p, '<')) {
        const char *close = p + 1 + strcspn(p + 1, "<>"), *name = p + 1, *name_end, *value, *value_end;
        if (*close != '>') {        /* "<" left open, or another "<" first: try from there */
            p = *close ? close : NULL;
            if (!p) break;
            continue;
        }
        name_end = memchr(name, ':', (size_t)(close - name));
        value = name_end ? name_end + 1 : close;
        value_end = close;
        if (!name_end) name_end = close;
        trim(&name, &name_end);
        trim(&value, &value_end);
        if (name < name_end && same_name(name, (size_t)(name_end - name), key)) {
            found = value;
            found_end = value_end;
        }
        p = close + 1;
    }
    if (!found) return -1;
    length = (size_t)(found_end - found);
    if (out && size) {
        size_t copied = length < size - 1 ? length : size - 1;
        memcpy(out, found, copied);
        out[copied] = '\0';
    }
    return (int)length;
}
