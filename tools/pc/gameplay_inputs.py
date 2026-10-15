"""Controller timelines shared by gameplay and state-replay regressions."""


def retail_ritual_inputs():
    events = [
        (int(part.split(":")[0]), part.split(":")[1])
        for part in ritual_inputs().split(",")
    ]
    # The unmodified recipe needs Gaia, Kuriboh and Beaver Warrior. The
    # latter two are in hand slot 3 on their respective turns in this deck.
    events += [(13900, "0020"), (13906, "0000"), (18900, "0020"), (18906, "0000")]
    return ",".join(f"{f}:{b}" for f, b in sorted(events))


def ritual_inputs(failure=False):
    events = [
        (int(part.split(":")[0]), part.split(":")[1])
        for part in inputs(magic=True).split(",")
        if int(part.split(":")[0]) < 10200
    ]
    events += [(11000, "0008")]
    if failure:
        # Slot 1 holds the ritual; one tribute cannot satisfy three slots.
        events += [(13800, "0020"), (14000, "4000"), (14400, "4000")]
    else:
        # Slot 2 holds a monster on the next two turns. Place each in a
        # different field column, then play the ritual from hand slot 0.
        events += [
            (13600, "0020"),
            (13800, "0020"),
            (14000, "4000"),
            (14400, "4000"),
            (14700, "0020"),
            (15000, "4000"),
            (15400, "4000"),
            (17000, "0008"),
            (18600, "0020"),
            (18800, "0020"),
            (19000, "4000"),
            (19400, "4000"),
            (19600, "0020"),
            (19800, "0020"),
            (20000, "4000"),
            (20400, "4000"),
            (22000, "0008"),
            (24000, "4000"),
            (24800, "4000"),
            (26000, "4000"),
            (26500, "4000"),
        ]
    events += [(f + 6, "0000") for f, _ in list(events) if f >= 11000]
    return ",".join(f"{f}:{b}" for f, b in sorted(events))


def animated_battle_inputs():
    events = [
        (int(part.split(":")[0]), part.split(":")[1])
        for part in inputs().split(",")
        if int(part.split(":")[0]) < 7100
    ]
    # Cast Tremendous Fire, let the CPU summon and attack, then summon
    # Man-eating Plant. Move across the field until Square selects its foe.
    events += [
        (7200, "2000"),
        (8000, "0020"),
        (8400, "4000"),
        (9000, "4000"),
        (9600, "4000"),
        (10200, "4000"),
        (11000, "0008"),
        (14000, "4000"),
        (14400, "4000"),
        (15000, "4000"),
        (15400, "4000"),
        (18000, "4000"),
        (18400, "8000"),
        (18600, "0020"),
        (18800, "8000"),
        (19000, "0020"),
        (19200, "8000"),
        (19400, "0020"),
        (19600, "8000"),
        (19800, "0020"),
        (20000, "8000"),
    ]
    events += [(f + 6, "0000") for f, _ in list(events) if f >= 7100]
    return ",".join(f"{f}:{b}" for f, b in sorted(events))


def deck_editor_inputs():
    events = [
        (int(part.split(":")[0]), part.split(":")[1])
        for part in inputs().split(",")
        if int(part.split(":")[0]) < 7100
    ]
    # Cycle every order in both panes, including shuffle, then remove a card.
    events += [(7100, "0020"), (7160, "0001"), (7230, "0008")]
    events += [(f, "0008") for f in range(7300, 8700, 200)]
    events += [(8700, "4000"), (8900, "0008"), (9100, "0080")]
    events += [(f, "0008") for f in range(9300, 10700, 200)]
    events += [(10600, "0001"), (10650, "0008")]
    # Card 24 was removed from the ID-sorted deck. Find it in the chest,
    # inspect it, return it to the deck, exercise page buttons and leave.
    events += [(f, "0040") for f in range(10700, 11850, 50)]
    events += [
        (12000, "1000"),
        (12400, "2000"),
        (12800, "4000"),
        (13200, "0020"),
        (13600, "0800"),
        (14000, "0400"),
        (14400, "0200"),
        (14800, "0100"),
        (15200, "2000"),
        (15900, "4000"),
        (16300, "4000"),
    ]
    events += [(f + 6, "0000") for f, _ in list(events) if f >= 7100]
    return ",".join(f"{f}:{b}" for f, b in sorted(events))


def deck_sorted_add_inputs():
    events = [
        (int(part.split(":")[0]), part.split(":")[1])
        for part in inputs().split(",")
        if int(part.split(":")[0]) < 7100
    ]
    # Keep the deck in ID order. Remove its lowest card (24), then add it
    # into the vacant last slot: Darwin qsort compares a temporary row here.
    events += [(7100, "0020"), (7500, "4000"), (7900, "0080")]
    events += [(f, "0040") for f in range(8100, 9250, 50)]
    events += [(9600, "4000")]
    events += [(f + 6, "0000") for f, _ in list(events) if f >= 7100]
    return ",".join(f"{f}:{b}" for f, b in sorted(events))


def inputs(third=False, magic=False):
    events = [
        (700, "0008"),
        (800, "4000"),
        (950, "4000"),
        (1200, "4000"),
        (1300, "0008"),
        (1400, "4000"),
        (1550, "4000"),
    ]
    events += [(f, "4000") for f in range(1700, 7100, 100)]
    if magic:
        events += [
            (7200, "2000"),
            (8000, "4000"),
            (8400, "4000"),
            (9000, "4000"),
            (9600, "4000"),
            (10200, "4000"),
        ]
        events += [(f + 6, "0000") for f, _ in list(events)]
        return ",".join(f"{f}:{b}" for f, b in sorted(events))
    events += [(7200, "2000"), (8000, "0010"), (8200, "0020")]
    if third:
        events += [(8300, "0020")]
    events += [
        (8400, "0010"),
        (8600, "4000"),
        (9000, "4000"),
        (9600, "4000"),
        (10200, "4000"),
    ]
    events += [(f + 6, "0000") for f, _ in list(events)]
    return ",".join(f"{f}:{b}" for f, b in sorted(events))
