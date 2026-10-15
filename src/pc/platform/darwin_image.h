#ifndef MEMORIES_DARWIN_IMAGE_H
#define MEMORIES_DARWIN_IMAGE_H
#include <stdint.h>
/* Initialize on the main thread before installing signal handlers. Returns
 * the ASLR-adjusted __TEXT,__text range of the actual loaded executable. */
/* Available after TextRange initializes the executable metadata cache. */
const char *DarwinImage_UUID(void);
int DarwinImage_TextRange(uintptr_t *first, uintptr_t *last);
#endif
