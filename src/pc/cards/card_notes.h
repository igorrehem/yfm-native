#ifndef MEMORIES_PC_CARD_NOTES_H
#define MEMORIES_PC_CARD_NOTES_H
#include <stddef.h>
/* A card's notes: the "notes" of its "cards" entries (notes/more-cards.md),
 * free text the game itself never reads. The modder writes down what they
 * changed or mean to, and a code mod may read tags from it, as RPG Maker's
 * note boxes are read:
 *
 *     <burn: 300>     the tag "burn", its value "300"
 *     <no-fusion>     the tag "no-fusion", its value ""
 *
 * A tag's name is anything but '<', '>' and ':', its spaces around it left
 * out, and any case matches; its value is what follows the colon up to the
 * '>', spaces around it left out. Anything outside the brackets is comment.
 * When a card's notes name a tag twice, the last one counts. */

/* The value of tag `key` in `notes`, written to `out` (cut to fit, always
 * ended with a '\0' when size is not 0) and its whole length returned, as
 * snprintf does; -1 when the notes have no such tag. */
int CardNotes_Tag(const char *notes, const char *key, char *out, size_t size);

#endif
