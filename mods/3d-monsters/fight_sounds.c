/* The fighters' own sounds, as the 3D arena plays them.
 *
 * Each MODEL.MRG record carries its monster's sounds: sector 224 is the
 * sequence bank the arena registers (SD_LoadSequenceBankPair: 32 driver ids,
 * each with a note record), sectors 225-274 the ADPCM samples it puts in SPU
 * RAM at 0xD810 (+0x19000 for the second slot), and sector 275 starts with
 * the slot's sound_entries, which the load copies even when it is quiet.
 * In the arena func_8005106C plays an entry when the slot's row is the
 * entry's and its time passes the entry's: SD_SEPlay(0x4000 | id), which
 * the driver turns through the bank into the note's voice.
 *
 * In the duel none of that can be loaded where the arena has it: the bank
 * goes to 0x801A8000, which holds the opponent's AI script, registering it
 * drops every sound id the duel registered (func_8004763C), and the samples
 * would go over the duel's own in SPU RAM, which the duel and its music
 * leave all but 39 KB of. So the sounds are decoded here and played by the
 * host (host->sound_add, API 12), on the sound-effect channels the audio
 * replacement mixes (src/pc/audio/replace.c), under the sound-effect volume.
 * Each note plays as the driver's sound-effect voice would play it
 * (func_8004803C): at its own pitch against the voices' sample note 0x3C00,
 * at its volume, and keyed off after its timer (timer << 2 ticks, one a
 * VBlank). The rows' XA entries (0x8000), the arena's voice clips off the
 * disc, are the game's own to play, as the arena plays them: func_80045334
 * readies one on the row's first frame, SD_SEPlay starts it at its time. */
#include "fight_sounds.h"
#include "game/sound.h"
#include "game/sound_pending_entries.h"
#include "game/sound_output_state.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SECTOR 2048
#define BANK_SECTOR 224           /* in the record: the sequence bank */
#define SAMPLE_SECTORS 50         /* then the ADPCM samples */
#define SIDES 2
#define BANK_ENTRIES 32
#define ENTRIES MODEL_SLOT_SOUND_ENTRY_COUNT
#define ENTRY_XA 0x8000
#define SAMPLE_NOTE 0x3C00        /* the sound-effect voices' (sd_init_voice_state.c) */
#define PITCH_ONE 0x1000          /* the SPU's pitch for 44.1 kHz */
#define TICKS_PER_TIMER 4         /* func_8004803C: voice_timer = timer << 2 */
#define TICKS_PER_SECOND 60
#define RELEASE_DIVISOR 200       /* the fade at a timer's end: 5 ms */

static const MemoriesModHost *host;

typedef struct {
    int sound[BANK_ENTRIES];      /* host handles, 0 none */
    int volume[BANK_ENTRIES];     /* the note's, 0-127 */
    ModelSlotSoundEntry entries[ENTRIES];
    int row, last;                /* the row it is in, and its time at the last call */
} Side;
static Side sides[SIDES];

static void say(const char *format, ...)
{
    char message[512];
    va_list arguments;
    if (!host->log_enabled(host)) return;
    va_start(arguments, format);
    vsnprintf(message, sizeof(message), format, arguments);
    va_end(arguments);
    host->log(host, "%s", message);
}

void FightSounds_Init(const MemoriesModHost *from)
{
    host = from;
}

static int playable(void)
{
    return host && host->api >= 12 && host->sound_add && host->sound_play && host->sound_free;
}

/* The library's integer note-to-pitch (src/pc/sdk/libspu.c, as libspu has
 * it): semitones in the high byte and 128ths below, 1536 to an octave,
 * stepped in 1/32-octave ratios of 0x103B / 0x1000 and interpolated. */
static u32 octave_pitch(u32 base, u32 units)
{
    u32 low = base << 12, factor = 0x103B, high = base * factor, i;
    for (i = 0; i < units / 32; i++) {
        low = base * factor;
        factor = (factor * 0x103B) >> 12;
        high = base * factor;
    }
    return (low + ((high - low) >> 5) * (units % 32)) >> 12;
}

static u32 note_pitch(u32 note)
{
    int difference = (int)(((note >> 8) << 7) + (note & 0xFF)) - (int)(((SAMPLE_NOTE >> 8) << 7) + (SAMPLE_NOTE & 0xFF));
    int distance = difference < 0 ? -difference : difference, octave = distance / 1536, units = distance % 1536;
    u32 base, pitch;
    if (difference >= 0) {
        base = (u32)PITCH_ONE << octave;
    } else {
        if (units) {
            octave++;
            units = 1536 - units;
        }
        base = (u32)PITCH_ONE >> octave;
    }
    pitch = octave_pitch(base & 0xFFFF, (u32)units);
    return pitch >= 0x4000 ? 0x3FFF : pitch;
}

/* The SPU's ADPCM, from `at` to the block that ends the sample (or the end
 * of the samples): 16-byte blocks of a shift and filter byte, a flags byte
 * and 28 four-bit samples. Returns the samples decoded into `out`. */
static size_t decode_adpcm(const u8 *samples, size_t size, size_t at, s16 *out, size_t room)
{
    static const int k0[5] = {0, 60, 115, 98, 122}, k1[5] = {0, 0, -52, -55, -60};
    int s1 = 0, s2 = 0;
    size_t count = 0;
    while (at + 16 <= size && count + 28 <= room) {
        const u8 *block = samples + at;
        int shift = block[0] & 0xF, filter = (block[0] >> 4) & 7, i;
        if (shift > 12) {
            shift = 9; /* as the hardware treats 13 to 15 */
        }
        if (filter > 4) {
            filter = 4;
        }
        for (i = 0; i < 28; i++) {
            int nibble = (block[2 + i / 2] >> ((i & 1) * 4)) & 0xF;
            int sample = (s16)(nibble << 12) >> shift;
            sample += (s1 * k0[filter] + s2 * k1[filter] + 32) >> 6;
            sample = sample > 32767 ? 32767 : sample < -32768 ? -32768 : sample;
            out[count++] = (s16)sample;
            s2 = s1;
            s1 = sample;
        }
        at += 16;
        if (block[1] & 1) {
            break; /* the end of the sample, looped or not: once is what plays */
        }
    }
    return count;
}

static void release_side(int side)
{
    Side *s = &sides[side];
    int j;
    for (j = 0; j < BANK_ENTRIES; j++) {
        if (s->sound[j] && playable()) {
            host->sound_free(host, s->sound[j]);
        }
    }
    memset(s, 0, sizeof(*s));
}

void FightSounds_Release(void)
{
    int side;
    for (side = 0; side < SIDES; side++) {
        release_side(side);
    }
}

/* Note `j` of the bank as the host's sound: the voice's pitch, cut at its
 * timer with a short fade, as the driver keys it off there. */
static int make_sound(const SDSeqBlock *bank, const u8 *samples, int j, s16 *scratch, size_t room)
{
    const SDNote *note = &bank->data[j];
    u32 pitch = note_pitch(note->pitch), rate = 44100u * pitch / PITCH_ONE;
    size_t count, cut, fade, i;
    if (!rate) {
        return 0;
    }
    count = decode_adpcm(samples, (size_t)SAMPLE_SECTORS * SECTOR, (size_t)note->field_0006 << 4, scratch, room);
    cut = note->timer ? (size_t)note->timer * TICKS_PER_TIMER * rate / TICKS_PER_SECOND : count;
    if (cut < count) {
        fade = rate / RELEASE_DIVISOR;
        fade = fade > cut ? cut : fade;
        for (i = 0; i < fade; i++) {
            scratch[cut - fade + i] = (s16)(scratch[cut - fade + i] * (int)(fade - i) / (int)fade);
        }
        count = cut;
    }
    if (!count) {
        return 0;
    }
    return host->sound_add(host, scratch, count, 1, rate);
}

void FightSounds_Load(int side, int record_lba, const ModelSlotSoundEntry *entries, unsigned rows)
{
    Side *s;
    u8 *data;
    s16 *scratch;
    const SDSeqBlock *bank;
    size_t room = (size_t)SAMPLE_SECTORS * SECTOR / 16 * 28;
    int i, read, made = 0;
    uint64_t started = host ? host->now_us(host) : 0, decoded = 0;

    if (side < 0 || side >= SIDES) {
        return;
    }
    release_side(side);
    if (!playable() || record_lba < 0 || !entries) {
        return;
    }
    s = &sides[side];
    memcpy(s->entries, entries, sizeof(s->entries));
    data = malloc((size_t)(1 + SAMPLE_SECTORS) * SECTOR);
    scratch = malloc(room * sizeof(*scratch));
    if (!data || !scratch) {
        free(data);
        free(scratch);
        return;
    }
    read = host->disc_read(host, record_lba + BANK_SECTOR, 1 + SAMPLE_SECTORS, data);
    decoded = host->now_us(host);
    bank = (const SDSeqBlock *)data;
    if (read == 1 + SAMPLE_SECTORS && bank->count > 0 && bank->count <= BANK_ENTRIES) {
        for (i = 0; i < ENTRIES && s->entries[i].frame; i++) {
            int j = s->entries[i].id & (BANK_ENTRIES - 1); /* as SD_SEPlay masks it */
            if ((s->entries[i].flags & ENTRY_XA) || s->entries[i].frame >= 32 || !(rows >> s->entries[i].frame & 1) ||
                j >= bank->count || s->sound[j] || bank->keys[j] == 0xFFFF) {
                continue;
            }
            s->sound[j] = make_sound(bank, data + SECTOR, j, scratch, room);
            if (s->sound[j] < 0) {
                s->sound[j] = 0;
            }
            s->volume[j] = bank->data[j].volume;
            made += s->sound[j] != 0;
        }
    }
    say("sound: side %d has %d sounds (read in %d us, made in %d us)\n", side, made, (int)(decoded - started),
        (int)(host->now_us(host) - decoded));
    free(scratch);
    free(data);
}

/* The entries of `row` with times from `from` up to `to`, not including it;
 * `first` on the row's first frame, when the arena readies its XA clips. */
static void play_span(Side *s, int row, int from, int to, int first)
{
    int i;
    for (i = 0; i < ENTRIES && s->entries[i].frame; i++) {
        const ModelSlotSoundEntry *e = &s->entries[i];
        int time = e->flags & 0x7FFF, j = e->id & (BANK_ENTRIES - 1);
        if (e->frame != row) {
            continue;
        }
        if (e->flags & ENTRY_XA) {
            if (first) {
                func_80045334(ENTRY_XA | e->id);
            }
            if (time >= from && time < to) {
                SD_SEPlay(ENTRY_XA | e->id, 0xFF, 0);
                say("sound: row %d, XA 0x%X at %d\n", row, ENTRY_XA | e->id, time);
            }
            continue;
        }
        if (time < from || time >= to || !s->sound[j]) {
            continue;
        }
        /* func_8004803C: (note volume * 0xFF) >> 1 against the voice's 0x3FFF. */
        host->sound_play(host, s->sound[j], s->volume[j] * 2 > 255 ? 255 : s->volume[j] * 2, 0);
        say("sound: row %d, note %d at %d\n", row, j, time);
    }
}

void FightSounds_Update(int side, const ModelSlot *slot, int playing)
{
    Side *s;
    int row, at, length, from, first;
    if (side < 0 || side >= SIDES || !playable()) {
        return;
    }
    s = &sides[side];
    row = slot->field_BF5;
    if (!playing) {
        s->row = 0;
        return;
    }
    at = slot->field_E06;
    length = slot->field_750[row].max << 4;
    first = s->row != row;
    from = first ? 0 : s->last;
    s->row = row;
    s->last = at;
    if (at >= from) {
        play_span(s, row, from, at, first);
    } else {
        play_span(s, row, from, length, 0); /* it wrapped round */
        play_span(s, row, 0, at, 0);
    }
}
