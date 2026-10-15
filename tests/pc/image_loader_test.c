#define _POSIX_C_SOURCE 200809L
#include "pc/compat/fs.h"
#include "scratch.h"
#include "pc/guest/image_loader.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static unsigned char expected[0x810];
static int calls;
int Memories_GuestLoadExeData(const unsigned char *data, size_t length, const char *name)
{
    assert(name && length == sizeof(expected) && !memcmp(data, expected, length));
    ++calls;
    return 17;
}
int main(void)
{
    char path[SCRATCH_MAX];
    MemoriesExeImage image = {0}, saved;
    int fd;
    scratch_template(path, sizeof(path), "memories-image");
    fd = mkstemp(path);
    assert(fd >= 0);
    memcpy(expected, "PS-X EXE", 8);
    Memories_StoreLE32(expected + 0x18, 0x80010000u);
    Memories_StoreLE32(expected + 0x1c, 16);
    Memories_StoreLE32(expected + 0x10, 0x80010000u);
    assert(!Memories_ParseExe(expected, sizeof(expected), 0, &image));
    assert(!Memories_ParseExe(expected, sizeof(expected), 1, &image));
    assert(image.address == 0x80010000u && image.size == 16 && image.entry == image.address);
    saved = image;
    assert(Memories_ParseExe(expected, sizeof(expected) - 1, 0, &image));
    assert(image.data == saved.data && image.address == saved.address && image.size == saved.size);
    assert(write(fd, expected, sizeof(expected)) == sizeof(expected));
    assert(!close(fd));
    assert(Memories_GuestLoadExe(path) == 17 && calls == 1);
    assert(!unlink(path));
    assert(Memories_GuestLoadExe(path) == -1 && calls == 1);
    /* Preserve fixed-backend data-only images, without relaxing translated entry checks. */
    Memories_StoreLE32(expected + 0x1c, 0);
    Memories_StoreLE32(expected + 0x10, 0);
    assert(!Memories_ParseExe(expected, sizeof(expected), 0, &image));
    assert(Memories_ParseExe(expected, sizeof(expected), 1, &image));
    Memories_StoreLE32(expected + 0x18, 0x80200001u);
    assert(Memories_ParseExe(expected, sizeof(expected), 0, &image));
    puts("Shared EXE loader: file IO, bounds, failure atomicity and backend entry policies passed");
    return 0;
}
