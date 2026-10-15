#ifndef MEMORIES_PC_DISC_SOURCE_H
#define MEMORIES_PC_DISC_SOURCE_H
/* Where the game's sectors come from: the player's raw (MODE2/2352) image of
 * the USA disc, or the folder tools/pc/extract_disc.py writes from it once,
 * named by its index, yfm-disc.txt. In the folder the disc's files are plain
 * files (SLUS_014.11, DATA/MODEL.MRG...); every sector is rebuilt from them
 * exactly as it is on the disc, framing and EDC/ECC included, so the drive
 * model (libds.c) cannot tell the two apart.
 *
 * yfm-disc.txt, one entry a line, in sector order and covering every sector once:
 *   yfm-disc 1
 *   sectors <count>
 *   source-sha256 <the image's SHA-256>        (informational)
 *   data <first> <count> <size> <subheader> <last subheader> <path>
 *       a file of MODE2/Form1 sectors, its <size> bytes as the file system has them
 *   raw <first> <count> <sector offset> <path>
 *       2352-byte sectors as they are on the disc (audio, video, the system area)
 * Paths are relative to the index's folder. */
#include <stddef.h>

#define DISC_SOURCE_SECTOR 2352
#define DISC_SOURCE_INDEX "yfm-disc.txt"

typedef struct DiscSource DiscSource;

/* A .bin image or a yfm-disc.txt index. NULL with the reason in `why`. */
DiscSource *DiscSource_Open(const char *path, char *why, size_t why_size);
void DiscSource_Close(DiscSource *source);
int DiscSource_Sectors(const DiscSource *source);
/* The whole 2352-byte sector `lba`: 1, or 0 outside the disc or on a read
 * error. Async-signal-safe (no allocation, no stdio). */
int DiscSource_Read(DiscSource *source, int lba, unsigned char *out);
/* Whether `path` names an index rather than an image (by its name). */
int DiscSource_IsIndex(const char *path);

#endif
