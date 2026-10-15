#ifndef MEMORIES_PC_GAME_FILES_H
#define MEMORIES_PC_GAME_FILES_H
/* The player's own copy of the game, the USA disc, SLUS-01411: a raw
 * (MODE2/2352) image, the .bin of a .bin/.cue pair, or the folder
 * tools/pc/extract_disc.py extracts from it once, named by its index
 * yfm-disc.txt (disc_source.h). Nothing of the game ships with the port, so
 * this is the one thing a player has to bring.
 *
 * MEMORIES_DISC names it outright. Otherwise the remembered selection, then the disc is taken
 * from, in turn: the `game` folder beside the executable, the folder of the
 * executable itself, the `game` folder in the user directory (paths.h), and
 * `game` in the current directory. In each, an extracted folder comes first,
 * then any image; a .bin that is not that disc is passed over. */
#include <stddef.h>
#include <stdio.h>

/* The disc's path (an image or a yfm-disc.txt), or NULL with the reason
 * (for the player) in `why`. */
const char *GameFiles_Disc(char *why, size_t why_size);
/* Interactive first-run setup when discovery fails. 1: ready, 0: cancelled,
 * -1: failed. Headless and explicit MEMORIES_DISC failures never prompt. */
int GameFiles_Setup(char *why, size_t why_size);
/* Validate and remember a selected image. 0 on success, -1 with why. */
int GameFiles_SelectDisc(const char *path, char *why, size_t why_size);
/* The game's executable, SLUS_014.11, read out of the disc into a fresh
 * buffer (free it). NULL when it cannot be read. */
unsigned char *GameFiles_ReadExecutable(const char *disc, size_t *size);

/* Plain reads of a raw (2352) image, for other discs of the game too (the
 * PAL discs of Game > Language, language.h): the 2048 bytes of user data of
 * sector `lba`, and where the ISO 9660 file `path` is ("DATA/WA_MRG.MRG",
 * names without ";1"). 1 on success. */
int GameFiles_ReadSector(FILE *file, unsigned lba, unsigned char *out);
int GameFiles_FindFile(FILE *file, const char *path, unsigned *lba, unsigned *size);

#endif
