#include "translated_image.h"
#include "image_loader.h"
#include <string.h>

int Memories_LoadTranslatedExe(MemoriesMemory *memory, const uint8_t *data,
                              size_t length, uint32_t *entry)
{
    MemoriesExeImage image;
    void *destination;
    if (!memory || !entry || Memories_ParseExe(data, length, 1, &image)) return -1;
    destination = Memories_Resolve(memory, image.address, image.size, 4);
    if (!destination) return -1;
    memcpy(destination, image.data, image.size);
    *entry = image.entry;
    return 0;
}
