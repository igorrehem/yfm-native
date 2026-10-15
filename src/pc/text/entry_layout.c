/* The text entries' table, the US executable's or the PAL one (entry_layout.h). */
#include "entry_layout.h"
#include <string.h>

/* The game's (duel_effect.h, duel_effect_entry_ranges.h): the US table,
 * pinned at 0x800EB288, and the channels' boundaries, u16[6] (the five and
 * a padding halfword). */
extern char D_800EB288[];
extern unsigned short gDuelEffect_awEntryRangeBoundaries[];

/* The PAL executables' boundaries (SLES_039.47-51, file offset 0x82650 in
 * the English one, 0x82A64 in the others; the US ones are at 0x80090E58),
 * and where the port keeps their 800 entries: 0x801F8000-0x801FD780. Below
 * it the sound driver's music package at 0x801EA800 runs to 0x801F4800 at
 * most (20 sectors, SD_RequestMusicPackageLoad); above it nothing. */
static const unsigned short pal_ranges[TEXT_ENTRY_CHANNELS + 1] = {0, 280, 500, 720, TEXT_ENTRY_PAL_COUNT};
static const unsigned short us_ranges[TEXT_ENTRY_CHANNELS + 1] = {0, 255, 415, 575, TEXT_ENTRY_US_COUNT};
static const unsigned short *launch_ranges = us_ranges;
static int started;

typedef char pal_entries_fit_guest_ram[
    (TEXT_ENTRY_PAL_POOL + TEXT_ENTRY_PAL_COUNT * TEXT_ENTRY_SIZE <= 0x80200000u) ? 1 : -1];

void TextEntries_UseLayout(int pal) { launch_ranges = pal ? pal_ranges : us_ranges; }

void TextEntries_Start(void)
{
    started = 1;
    memcpy(gDuelEffect_awEntryRangeBoundaries, launch_ranges, sizeof(us_ranges));
}

static int pal_layout(void)
{
    return gDuelEffect_awEntryRangeBoundaries[TEXT_ENTRY_CHANNELS] == TEXT_ENTRY_PAL_COUNT;
}

void *TextEntries_Pool(void)
{
    return pal_layout() ? (void *)(unsigned long)TEXT_ENTRY_PAL_POOL : (void *)D_800EB288;
}

int TextEntries_Total(void) { return pal_layout() ? TEXT_ENTRY_PAL_COUNT : TEXT_ENTRY_US_COUNT; }

int TextEntries_PageLetters(int channel)
{
    const unsigned short *ranges = started ? gDuelEffect_awEntryRangeBoundaries : launch_ranges;
    if (channel < 0 || channel >= TEXT_ENTRY_CHANNELS) return 0;
    return ranges[channel + 1] - ranges[channel] - 1;
}
