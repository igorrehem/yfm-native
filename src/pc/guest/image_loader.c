/* File IO is the same for fixed and translated guest images. */
#include "pc/compat/fs.h"
#include "image.h"
#include <stdio.h>
#include <stdlib.h>

int Memories_GuestLoadExe(const char *path)
{
    unsigned char *data;
    long length;
    int result;
    FILE *file = fopen(path, "rb");
    if (!file || fseek(file, 0, SEEK_END) || (length = ftell(file)) < 0 ||
        fseek(file, 0, SEEK_SET) || !(data = malloc(length ? (size_t)length : 1))) {
        fprintf(stderr, "%s: not a readable PS-X executable\n", path);
        if (file) fclose(file);
        return -1;
    }
    if (fread(data, 1, (size_t)length, file) != (size_t)length) length = 0;
    fclose(file);
    result = Memories_GuestLoadExeData(data, (size_t)length, path);
    free(data);
    return result;
}
