#include "types.h"
#include "pc/guest/translated_runtime.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef void (*Callback)(int);
struct Record { u8 *G32 bytes; Callback G32 callback; };
_Static_assert(sizeof(struct Record) == 8, "guest record layout");
extern u8 read_stream(struct Record *);
extern void write_stream(struct Record *, u8);
extern u8 *get_stream(struct Record *);
extern void set_stream(struct Record *, u8 *);
extern u8 *guest_cast(u32);
extern u32 native_cast(u8 *);
extern u8 read_absolute(void);
extern u8 read_pinned(void);
extern void invoke(struct Record *, int);
extern u32 atomic_read(u32 *);
extern void atomic_write(u32 *, u32);
extern u32 atomic_add(u32 *);
extern int atomic_exchange(u32 *, u32 *, u32);
struct WidePair { u64 first, second; };
extern u64 sum_pair(struct WidePair);
extern void *checked_copy(void *, const void *, u32);
extern void *checked_set(void *, int, u32);
extern int checked_format(char *, const char *);
extern void invoke_guest_table(int);
extern void store_constant_callback(u8 *);
extern void checked_sort(void *, u32);
static int received;
void constant_callback(int value) { received = value; }
static void callback(int value) { received = value; }
int main(void)
{
    MemoriesMemory *memory = calloc(1, sizeof(*memory));
    struct Record *record, *pinned;
    u8 *bytes;
    assert(memory && GuestRuntime_Bind(memory) == 0);
    record = Memories_Resolve(memory, 0x80014000u, sizeof(*record), 4);
    pinned = Memories_Resolve(memory, 0x80018000u, sizeof(*pinned), 4);
    bytes = Memories_Resolve(memory, 0x80012000u, 4, 1);
    assert(record && pinned && bytes && (uintptr_t)bytes > UINT32_MAX);
    bytes[0] = 12; bytes[1] = 13;
    record->bytes = (u8 *G32)(uintptr_t)0xa0012000u;
    assert(read_stream(record) == 12);
    assert((uintptr_t)record->bytes == 0xa0012001u);
    write_stream(record, 99);
    assert(bytes[3] == 99);
    assert((uintptr_t)get_stream(record) == 0xa0012001u);
    set_stream(record, bytes);
    assert((uintptr_t)record->bytes == 0x80012000u);
    assert(native_cast(bytes) == 0x80012000u);
    assert((uintptr_t)guest_cast(0xa0012000u) == 0xa0012000u);
    pinned->bytes = (u8 *G32)(uintptr_t)0x80012001u;
    assert(read_pinned() == 13);
    *(u8 *)Memories_Resolve(memory, 0x8009B363u, 1, 1) = 71;
    assert(read_absolute() == 71);
    assert(GuestRuntime_RegisterFunction(0x80019000u, (void (*)(void))callback) == 0);
    assert(GuestRuntime_RegisterFunction(0x801681a0u, (void (*)(void))constant_callback) == 0);
    u8 *object = Memories_Resolve(memory, 0x80013000u, 0x54, 4);
    assert(object); Memories_WriteLE32(object + 0x48, 0x11223344u); Memories_WriteLE32(object + 0x50, 0xaabbccddu);
    store_constant_callback((u8 *)(uintptr_t)0x80013000u);
    assert(Memories_ReadLE32(object + 0x4c) == 0x801681a0u);
    assert(Memories_ReadLE32(object + 0x48) == 0x11223344u && Memories_ReadLE32(object + 0x50) == 0xaabbccddu);
    ((Callback)GuestRuntime_ResolveFunction((void *)(uintptr_t)Memories_ReadLE32(object + 0x4c)))(77);
    assert(received == 77);
    record->callback = (Callback G32)(uintptr_t)0xa0019000u;
    invoke(record, 42);
    assert(received == 42);
    {
        Callback G32 *table = Memories_Resolve(memory, 0x80012600u, 8, 4);
        assert(table);
        table[0] = (Callback G32)(uintptr_t)0;
        table[1] = (Callback G32)(uintptr_t)0x80019000u;
        invoke_guest_table(19);
        assert(received == 19);
    }
    {
        u32 *guest_atomic = (u32 *)(uintptr_t)0xa0012100u;
        u32 expected = 13;
        struct WidePair pair = {0x100000000ull, 17};
        atomic_write(guest_atomic, 10);
        assert(atomic_read(guest_atomic) == 10);
        assert(atomic_add(guest_atomic) == 10);
        assert(atomic_exchange(guest_atomic, &expected, 27));
        assert(atomic_read(guest_atomic) == 27);
        assert(sum_pair(pair) == 0x100000011ull);
    }
    {
        void *destination = (void *)(uintptr_t)0x80012200u;
        const void *source = (const void *)(uintptr_t)0xa0012000u;
        u8 *copied = Memories_Resolve(memory, 0x80012200u, 4, 1);
        u8 *text = Memories_Resolve(memory, 0x80012300u, 3, 1);
        char *formatted = Memories_Resolve(memory, 0x80012400u, 8, 1);
        assert(checked_copy(destination, source, 4) == destination);
        assert(copied[0] == bytes[0] && copied[1] == bytes[1] && copied[3] == bytes[3]);
        assert(checked_set(destination, 0x5a, 4) == destination);
        assert(copied[0] == 0x5a && copied[3] == 0x5a);
        text[0] = 'o'; text[1] = 'k'; text[2] = 0;
        assert(checked_format((char *)(uintptr_t)0xa0012400u, (char *)(uintptr_t)0x80012300u) == 4);
        assert(formatted[0] == 'o' && formatted[1] == 'k' && formatted[2] == '1' && formatted[3] == '2' && formatted[4] == 0);
    }
    {
        struct SortRow { u32 key; u8 *G32 payload; u32 padding[2]; };
        struct SortRow *rows = Memories_Resolve(memory, 0x80015000u, 40 * sizeof(*rows), 4);
        u8 *values = Memories_Resolve(memory, 0x80016000u, 40, 1);
        unsigned regions = GuestRuntime_RegionCount();
        for (unsigned repeat = 0; repeat < 3; repeat++) {
            for (unsigned i = 0; i < 40; i++) {
                rows[i].key = values[i] = i == 39 ? 0 : i;
                rows[i].payload = (u8 *G32)(uintptr_t)(0x80016000u + i);
                rows[i].padding[0] = i;
            }
            checked_sort((void *)(uintptr_t)0x80015000u, 40);
            for (unsigned i = 0; i < 40; i++) {
                assert(rows[i].key == (i < 2 ? 0 : i - 1));
                assert(rows[i].key == values[rows[i].padding[0]]);
            }
            assert(GuestRuntime_RegionCount() == regions);
        }
    }
    GuestRuntime_Reset();
    free(memory);
    puts("IR pointer roundtrip, pinned/absolute globals and callback dispatch passed");
    return 0;
}
