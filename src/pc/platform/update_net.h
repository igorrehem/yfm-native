#ifndef MEMORIES_PC_UPDATE_NET_H
#define MEMORIES_PC_UPDATE_NET_H
/* One HTTP(S) GET for the update check (update_check.h): WinHTTP on
 * Windows, the curl program on Linux. Redirects are followed. Blocks, so
 * only the check's thread calls it. */
#include <stddef.h>

/* Takes each piece of the body as it arrives; nonzero stops the transfer. */
typedef int (*UpdateNetSink)(const void *data, size_t size, void *context);

/* 0 when the whole body arrived with status 200; else -1 and a short
 * reason for the player in `why`. `timeout_seconds` bounds the whole
 * transfer with curl, and each wait for the server with WinHTTP. */
int UpdateNet_Get(const char *url, int timeout_seconds, UpdateNetSink sink, void *context, char *why, size_t why_size);

#endif
