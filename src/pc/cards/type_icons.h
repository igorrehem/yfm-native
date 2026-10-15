#ifndef MEMORIES_PC_TYPE_ICONS_H
#define MEMORIES_PC_TYPE_ICONS_H

/* Custom monster type icons live in their own software-GPU bank.  The
 * returned cell is a normal 16x16 PSX sprite, so it works at 1x and uses the
 * source PNG at HD resolutions without replacing any retail type texture. */
void TypeIcons_Clear(void);
int TypeIcons_Cell(int type, int *tpage, int *u, int *v, int *clut);

/* The card viewer's and the card bar's type icon, drawn by func_80035E20
 * from a text entry's otherwise-unused code: func_80037DA4 marks the icon
 * it is about to add with the card's real type (TypeIcons_MarkIcon), taken
 * once by DuelEffect_AppendEntry (TypeIcons_TakeIconMark) into the entry, so
 * it reaches func_80035E20 even though the field the disc keys its own 24
 * built-in type icons by was left at the Dragon compatibility value
 * (cards.c). 0 where the disc's own icon stands, or a custom type with no
 * icon of its own. */
#define TYPE_ICON_CODE 0xE600u   /* no Shift-JIS character: E6 then the type's icon id */
void TypeIcons_MarkIcon(int type);
unsigned TypeIcons_TakeIconMark(void);
/* For a marked entry's code: the sprite's texture page, u, v and palette,
 * as an unpacked clut x, y (func_80035E20's sprites keep it that way) rather
 * than TypeIcons_Cell's combined clut. 0 for any other code. */
int TypeIcons_IconCell(unsigned code, int *tpage, int *u, int *v, int *clut_x, int *clut_y);
#endif
