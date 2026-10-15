/* Real loopback sockets: stalled readers must not hold the game thread. */
#define _POSIX_C_SOURCE 200809L
#include "pc/debug/control_net.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
typedef SOCKET Socket;
#define CLOSE closesocket
#define INVALID INVALID_SOCKET
static uint64_t now_ms(void) { return GetTickCount64(); }
#else
#include <arpa/inet.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
typedef int Socket;
#define CLOSE close
#define INVALID (-1)
static uint64_t now_ms(void)
{
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (uint64_t)now.tv_sec * 1000 + (uint64_t)now.tv_nsec / 1000000;
}
#endif

static int pumps, cancel_after;
static int idle(void)
{
    pumps++;
    return !cancel_after || pumps < cancel_after;
}

static Socket connect_client(unsigned port)
{
    struct sockaddr_in address;
    int small = 1024;
    Socket peer = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    assert(peer != INVALID);
    assert(!setsockopt(peer, SOL_SOCKET, SO_RCVBUF, (const char *)&small, sizeof(small)));
    memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = htons((unsigned short)port);
    assert(!connect(peer, (struct sockaddr *)&address, sizeof(address)));
    assert(ControlNet_Accept(1000));
    return peer;
}

static void round_trip(Socket peer)
{
    char buffer[8] = {0};
    assert(send(peer, "info\n", 5, 0) == 5);
    assert(ControlNet_Receive(buffer, sizeof(buffer), 1000) == 5);
    assert(!memcmp(buffer, "info\n", 5));
    assert(!ControlNet_Gone());
    assert(!ControlNet_Send("ok\n", 3, idle));
    assert(recv(peer, buffer, sizeof(buffer), 0) == 3);
    assert(!memcmp(buffer, "ok\n", 3));
}

int main(void)
{
    static char large[8 * 1024 * 1024];
    unsigned port;
    uint64_t started, elapsed;
    Socket peer;
    memset(large, 'x', sizeof(large));
    assert(!ControlNet_Listen(0, &port));
    peer = connect_client(port);
    round_trip(peer);

    /* The peer stays connected but never consumes the large reply. */
    pumps = 0;
    started = now_ms();
    assert(ControlNet_Send(large, sizeof(large), idle) == -1);
    elapsed = now_ms() - started;
    assert(elapsed >= 900 && elapsed < 3000);
    assert(pumps > 5); /* the game's callback keeps servicing its window */
    ControlNet_Drop();
    CLOSE(peer);
    assert(ControlNet_Gone());

    /* The listener survives the timeout and serves a fresh connection. */
    peer = connect_client(port);
    round_trip(peer);
    pumps = 0;
    cancel_after = 3; /* the window asked to close while a send was pending */
    started = now_ms();
    assert(ControlNet_Send(large, sizeof(large), idle) == -1);
    assert(pumps == cancel_after && now_ms() - started < 1000);
    ControlNet_Drop();
    CLOSE(peer);
    cancel_after = 0;

    peer = connect_client(port);
    round_trip(peer);
    ControlNet_Drop();
    CLOSE(peer);
    puts("control net: timeout, cancellation, event pumping, and reconnect passed");
    return 0;
}
