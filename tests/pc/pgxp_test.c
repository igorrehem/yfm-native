#include "pc/compat/pgxp.h"
#include "pc/compat/gte.h"
#include <assert.h>

int main(void)
{
    uint32_t packet[] = {0x04ffffff, 0x20000000, 0x0014000a, 0x00140014, 0x001e000a};
    uint32_t address = ((uint32_t)(uintptr_t)packet & 0x00ffffffu) + 8;
    float a[] = {10.25f, 20.5f, 100.0f}, b[] = {10.75f, 20.5f, 120.0f};
    float x, y, w;
    Pgxp_Active = 1;
    Pgxp_Project(packet[2], a[0], a[1], a[2]);
    Pgxp_Project(packet[2], b[0], b[1], b[2]);
    assert(!Pgxp_Find(packet[2], &x, &y, &w)); /* ambiguous by value */
    Pgxp_Stored(packet[2], a);
    Pgxp_AddPrim(packet);
    assert(Pgxp_FindAt(address, packet[2], &x, &y, &w) == 1 && x == a[0]);

    /* The same packet buffer is reused for a primitive without GTE stores.
     * An unchanged rounded word must not inherit the previous projection. */
    Pgxp_AddPrim(packet);
    assert(Pgxp_FindAt(address, packet[2], &x, &y, &w) == 0);
    Pgxp_Stored(packet[2], a);
    Pgxp_Stored(packet[2], b);
    Pgxp_AddPrim(packet);
    assert(Pgxp_FindAt(address, packet[2], &x, &y, &w) == -1);
    Pgxp_Stored(packet[2], a);
    Pgxp_AddPrim(packet);
    Pgxp_NextFrame();
    assert(Pgxp_FindAt(address, packet[2], &x, &y, &w) == 1);
    Pgxp_NextFrame();
    assert(Pgxp_FindAt(address, packet[2], &x, &y, &w) == 0);

    /* GsSortPoly copies the stored word moved by its offset: the packet's
     * word is (15, 17), and the precise position moves with it. */
    Pgxp_Stored(0x0014000a, a);
    packet[2] = 0x0011000f;
    Pgxp_AddPrimMoved(packet, 5, -3);
    assert(Pgxp_FindAt(address, packet[2], &x, &y, &w) == 1 && x == a[0] + 5 && y == a[1] - 3 && w == a[2]);

    /* Close to the camera: R11 = R33 = 0.5 put the vertex at view x -150.5,
     * z 160.5, which the GTE truncates to IR1 = -151 and SZ3 = 160 before
     * it divides. The word is -284, the vertex really at -281.3: outside the
     * (-1, +2) window, but that is the truncation, so the precise position
     * is kept. */
    Memories_GteReset();
    Memories_GteWriteControl(0, 0x0800);
    Memories_GteWriteControl(2, 0x1000);
    Memories_GteWriteControl(4, 0x0800);
    Memories_GteWriteControl(26, 300);
    Memories_GteWriteData(0, (uint16_t)-301);
    Memories_GteWriteData(1, 321);
    Memories_GteCommand(0x0180001); /* RTPS, sf */
    assert((int16_t)Memories_GteReadData(14) == -284);
    assert(Memories_GtePrecise(2, &x, &y, &w) && x > -281.32f && x < -281.30f && w == 160.5f);

    /* A view x IR1 saturates is not the word's vertex: rejected. */
    Memories_GteWriteControl(0, 0x7fff);
    Memories_GteWriteData(0, 0x7fff);
    Memories_GteCommand(0x0180001);
    assert(!Memories_GtePrecise(2, &x, &y, &w));

    /* PGXP: keep a full duel field at full speed rewrote the tables as two
     * per kind (this frame's and the last's, swapped each frame, TABLE_SIZE
     * 65536, PROBES 64). None of the words above hash to bucket 0 (checked
     * separately), so this exercises a bucket of its own.
     *
     * These 65 words are `Cinv * (0 * 65536 + k) mod 2^32` for k = 0..64,
     * the inverse of first()'s multiplier (2654435761, odd, so invertible
     * mod 2^32): each maps to bucket 0, so all 65 probe the same chain. */
    {
        static const uint32_t bucket0[65] = {
            0x00000000, 0x0e8b2f51, 0x1d165ea2, 0x2ba18df3, 0x3a2cbd44, 0x48b7ec95, 0x57431be6, 0x65ce4b37,
            0x74597a88, 0x82e4a9d9, 0x916fd92a, 0x9ffb087b, 0xae8637cc, 0xbd11671d, 0xcb9c966e, 0xda27c5bf,
            0xe8b2f510, 0xf73e2461, 0x05c953b2, 0x14548303, 0x22dfb254, 0x316ae1a5, 0x3ff610f6, 0x4e814047,
            0x5d0c6f98, 0x6b979ee9, 0x7a22ce3a, 0x88adfd8b, 0x97392cdc, 0xa5c45c2d, 0xb44f8b7e, 0xc2dabacf,
            0xd165ea20, 0xdff11971, 0xee7c48c2, 0xfd077813, 0x0b92a764, 0x1a1dd6b5, 0x28a90606, 0x37343557,
            0x45bf64a8, 0x544a93f9, 0x62d5c34a, 0x7160f29b, 0x7fec21ec, 0x8e77513d, 0x9d02808e, 0xab8dafdf,
            0xba18df30, 0xc8a40e81, 0xd72f3dd2, 0xe5ba6d23, 0xf4459c74, 0x02d0cbc5, 0x115bfb16, 0x1fe72a67,
            0x2e7259b8, 0x3cfd8909, 0x4b88b85a, 0x5a13e7ab, 0x689f16fc, 0x772a464d, 0x85b5759e, 0x9440a4ef,
            0xa2cbd440,
        };
        int i;

        /* Fill the bucket's own 64 probe slots this frame; each must round-
         * trip its own, distinct value. */
        for (i = 0; i < 64; i++) {
            Pgxp_Project(bucket0[i], (double)i, (double)i + 100.0, (double)i + 1000.0);
        }
        for (i = 0; i < 64; i++) {
            assert(Pgxp_Find(bucket0[i], &x, &y, &w) && x == (float)i && y == (float)i + 100.0f &&
                   w == (float)i + 1000.0f);
        }

        /* The 65th word in the same chain finds every probe taken: stored
         * nowhere (the comment's "stays at whole pixels"), and the 64
         * already there are untouched. */
        Pgxp_Project(bucket0[64], 500.0, 600.0, 700.0);
        assert(!Pgxp_Find(bucket0[64], &x, &y, &w));
        assert(Pgxp_Find(bucket0[0], &x, &y, &w) && x == 0.0f);
        assert(Pgxp_Find(bucket0[63], &x, &y, &w) && x == 63.0f);

        /* One frame on: the 64 are still readable (the last frame's table),
         * and this frame's half of the same bucket is free again -- a fresh
         * value for bucket0[0] does not collide with its own aged entry. */
        Pgxp_NextFrame();
        for (i = 0; i < 64; i++) {
            assert(Pgxp_Find(bucket0[i], &x, &y, &w) && x == (float)i);
        }
        Pgxp_Project(bucket0[0], 9000.0, 9100.0, 9200.0);
        assert(Pgxp_Find(bucket0[0], &x, &y, &w) && x == 9000.0f);
        /* bucket0[1], never re-stored this frame, still reads the aged one. */
        assert(Pgxp_Find(bucket0[1], &x, &y, &w) && x == 1.0f);

        /* A second frame on: the original 64 are gone (older than the last
         * frame), but bucket0[0]'s fresher value, one frame old now, holds. */
        Pgxp_NextFrame();
        assert(!Pgxp_Find(bucket0[1], &x, &y, &w));
        assert(Pgxp_Find(bucket0[0], &x, &y, &w) && x == 9000.0f);
    }

    /* The same crowding and swap behaviour for Pgxp_StoreAt/Pgxp_FindAt
     * (the `placed` table, keyed by address instead of word): only the
     * first() hashing is shared, so a lighter check is enough here. */
    {
        static const uint32_t bucket0[65] = {
            0x00000000, 0x0e8b2f51, 0x1d165ea2, 0x2ba18df3, 0x3a2cbd44, 0x48b7ec95, 0x57431be6, 0x65ce4b37,
            0x74597a88, 0x82e4a9d9, 0x916fd92a, 0x9ffb087b, 0xae8637cc, 0xbd11671d, 0xcb9c966e, 0xda27c5bf,
            0xe8b2f510, 0xf73e2461, 0x05c953b2, 0x14548303, 0x22dfb254, 0x316ae1a5, 0x3ff610f6, 0x4e814047,
            0x5d0c6f98, 0x6b979ee9, 0x7a22ce3a, 0x88adfd8b, 0x97392cdc, 0xa5c45c2d, 0xb44f8b7e, 0xc2dabacf,
            0xd165ea20, 0xdff11971, 0xee7c48c2, 0xfd077813, 0x0b92a764, 0x1a1dd6b5, 0x28a90606, 0x37343557,
            0x45bf64a8, 0x544a93f9, 0x62d5c34a, 0x7160f29b, 0x7fec21ec, 0x8e77513d, 0x9d02808e, 0xab8dafdf,
            0xba18df30, 0xc8a40e81, 0xd72f3dd2, 0xe5ba6d23, 0xf4459c74, 0x02d0cbc5, 0x115bfb16, 0x1fe72a67,
            0x2e7259b8, 0x3cfd8909, 0x4b88b85a, 0x5a13e7ab, 0x689f16fc, 0x772a464d, 0x85b5759e, 0x9440a4ef,
            0xa2cbd440,
        };
        int i;
        float known[3];

        for (i = 0; i < 64; i++) {
            known[0] = (float)i;
            known[1] = (float)i + 100.0f;
            known[2] = (float)i + 1000.0f;
            Pgxp_StoreAt(bucket0[i], 0xaaaa0000u + (uint32_t)i, known);
        }
        for (i = 0; i < 64; i++) {
            assert(Pgxp_FindAt(bucket0[i], 0xaaaa0000u + (uint32_t)i, &x, &y, &w) == 1 && x == (float)i);
        }
        /* Crowded: the 65th neither stores nor corrupts the chain. */
        known[0] = 1.0f;
        known[1] = 2.0f;
        known[2] = 3.0f;
        Pgxp_StoreAt(bucket0[64], 0xaaaa0040u, known);
        assert(Pgxp_FindAt(bucket0[64], 0xaaaa0040u, &x, &y, &w) == 0);
        assert(Pgxp_FindAt(bucket0[0], 0xaaaa0000u, &x, &y, &w) == 1 && x == 0.0f);
        assert(Pgxp_FindAt(bucket0[63], 0xaaaa003fu, &x, &y, &w) == 1 && x == 63.0f);
    }
    return 0;
}
