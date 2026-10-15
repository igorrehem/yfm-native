#ifndef MEMORIES_PC_ATTRIBUTES_H
#define MEMORIES_PC_ATTRIBUTES_H

/* Card attributes as data mods change them (notes/modding.md, "Attributes").
 *
 * A card record keeps its attribute in four bits.  The retail game uses
 * 0-5 (Light through Wind), and uses 6 and 7 internally for magic and trap
 * presentation.  Mods may rename 0-5 and add attributes to the port's
 * per-card attribute bank.  Cards, equip bonuses and monster-effect filters
 * accept either an id or any declared name. */

#define ATTRIBUTES_RETAIL 6
#define ATTRIBUTES_MAX 255       /* the card-detail record's icon key is u8 */

struct JsonValue;

void Attributes_Build(void);
void Attributes_Add(const char *mod, const struct JsonValue *manifest);
void Attributes_Clear(void);
/* Drop decoded icon cells and their HD sprite registrations after a registry
 * reset, before a new set of declarations can reuse the same ids. */
void Attributes_IconsClear(void);

/* A number 0-15, a retail or declared name, or -1 when it is not one. */
int Attributes_Value(const struct JsonValue *value);
int Attributes_Find(const char *name);
int Attributes_Valid(int attribute);
int Attributes_Declared(int attribute);
const char *Attributes_Name(int attribute);
const char *Attributes_Icon(int attribute);

/* A card's original packed nibble is still present for the console's code,
 * but PC card metadata keeps the real id here.  A mod-defined attribute
 * (8-255) is always drawn through this cell; a renamed retail attribute
 * (0-5) only is when the mod also gave it its own "icon" -- otherwise it
 * keeps drawing from the retail attribute strip, as if unrenamed. */
int Attributes_IconCell(int attribute, int *tpage, int *u, int *v, int *clut_x, int *clut_y);

#endif
