#include "types.h"
#include "pc/guest/translated_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern void AiScript_Init(u8 *);
extern s32 AiScript_Run(void);
extern void AiScript_EndHand(void), AiScript_EndField(void), AiScript_PlayFieldCard(void);
int VSync(int mode) { (void)mode; abort(); }
void test_guest_bzero(void *p, size_t length) { memset(GuestRuntime_ResolveData(p, length), 0, length); }
int main(void) {
    MemoriesMemory *memory = calloc(1, sizeof(*memory)); assert(memory && !GuestRuntime_Bind(memory));
    u8 *table = Memories_Resolve(memory, 0x800916e0, 68*4, 4);
    u8 *script = Memories_Resolve(memory, 0x801a8000, 16, 4);
    const u32 addresses[] = {0x80070ff8, 0x80071000, 0x80070f1c};
    void (*handlers[])(void) = {AiScript_EndHand, AiScript_EndField, AiScript_PlayFieldCard};
    const u8 opcodes[] = {13, 14, 12};
    for (unsigned i = 0; i < 3; i++) {
        assert(!GuestRuntime_RegisterFunction(addresses[i], handlers[i]));
        Memories_WriteLE32(table + 4*opcodes[i], addresses[i]);
        script[0] = opcodes[i]; /* Remaining operands/opcode zero are sentinels. */
        AiScript_Init((u8 *)(uintptr_t)0x801a8000);
        assert((AiScript_Run() == (s32[]){1,3,2}[i]));
    }
    GuestRuntime_Reset(); free(memory);
    puts("Real AI VM recognizes all three guest callback terminators before the next opcode");
}
