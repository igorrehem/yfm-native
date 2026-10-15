"""Weighted pools, worked out exactly as the port does (src/pc/cards/tables.c:
scale() and apply()), so the editor's pools, its Normalize button and the
edits it writes all come out as the game will have them."""
from __future__ import annotations

from .gamedata import POOL_TOTAL, DECK_POOL_MIN_CARDS


def scale(weights: dict, chosen, target: int) -> bool:
    """Scale the chosen cards' weights so they add up to `target`: each its
    share rounded down, the rest one each to the largest remainders, the
    lower id first between equals. False when there is nothing to scale."""
    chosen = sorted(cid for cid in chosen if weights.get(cid, 0))
    total = sum(weights[cid] for cid in chosen)
    if not total:
        return target == 0
    given = 0
    shares = []
    for cid in chosen:
        part = weights[cid] * target
        weights[cid] = part // total
        given += weights[cid]
        shares.append((-(part % total), cid))
    shares.sort()
    for _, cid in shares:
        if given >= target:
            break
        weights[cid] += 1
        given += 1
    return True


def apply_edit(pool: dict, listed: dict, replace: bool = False, deck: bool = False):
    """One mod's edit ({card: weight}, "replace") of a pool: the pool after
    it, or None when the port would refuse it and keep the pool as it was."""
    weights = {} if replace else dict(pool)
    for cid, weight in listed.items():
        weights[cid] = weight
    given = sum(weights.get(cid, 0) for cid in listed)
    rest = sum(w for cid, w in weights.items() if cid not in listed)
    if given >= POOL_TOTAL or not rest:
        weights = {cid: w for cid, w in weights.items() if cid in listed}
        if not scale(weights, list(weights), POOL_TOTAL) or not given:
            return None
    else:
        if not scale(weights, [cid for cid in weights if cid not in listed], POOL_TOTAL - given):
            return None
    weights = {cid: w for cid, w in weights.items() if w}
    if deck and len(weights) < DECK_POOL_MIN_CARDS:
        return None
    return weights


def normalize(pool: dict) -> dict:
    """The pool brought to exactly 2048, keeping its proportions."""
    weights = {cid: w for cid, w in pool.items() if w > 0}
    if not scale(weights, list(weights), POOL_TOTAL):
        return {}
    return {cid: w for cid, w in weights.items() if w}


def edit_for(retail: dict, edited: dict, deck: bool = False):
    """The shortest edit (listed weights, replace) that turns the retail pool
    into the edited one in the port, or None when they are the same.
    Changed cards alone do it when the edited pool adds up to 2048; if that
    does not come out exact, the whole pool is written with "replace"."""
    edited = {cid: w for cid, w in edited.items() if w}
    if edited == {cid: w for cid, w in retail.items() if w}:
        return None
    best = (dict(edited), True)
    changed = {cid: edited.get(cid, 0) for cid in set(retail) | set(edited) if edited.get(cid, 0) != retail.get(cid, 0)}
    if apply_edit(retail, changed, False, deck) == edited and len(changed) < len(best[0]):
        best = (changed, False)
    # Often less is needed: a card taken out or put in, the rest scaled as
    # the port scales them. Start from those, and list whatever still differs.
    listed = {cid: w for cid, w in changed.items() if not w or not retail.get(cid)}
    both = sorted(edited[cid] / retail[cid] for cid in retail if edited.get(cid) and retail[cid])
    if both:
        ratio = both[len(both) // 2]        # how much most cards, the unlisted ones, were scaled
        listed.update({cid: edited[cid] for cid in changed
                       if edited.get(cid) and retail.get(cid) and abs(edited[cid] - retail[cid] * ratio) > 1.5})
    for _ in range(8):
        if len(listed) >= len(best[0]):
            break
        result = apply_edit(retail, listed, False, deck)
        if result == edited:
            best = (dict(listed), False)
            break
        result = result or {}
        wrong = {cid for cid in set(result) | set(edited) if result.get(cid, 0) != edited.get(cid, 0)}
        listed.update({cid: edited.get(cid, 0) for cid in wrong})
    return best
