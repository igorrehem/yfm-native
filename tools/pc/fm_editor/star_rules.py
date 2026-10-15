"""Set stars by rule (the Guardian Stars tab's "Set stars by rule..."): many
cards' guardian stars at once, from a mapping of their attribute or monster
type to a star (a Fire card's first star is Fire, say), or one star for all
of them, for the cards a filter chooses (bulk_fusions.CardFilter, the Bulk
fusions window's). A plan comes first, to preview; apply() then keeps what it
changed so undo() can put back the cards nobody has edited since."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import guardian_stars
from .bulk_fusions import CardFilter

SOURCES = ("attribute", "type", "star")   # what picks the star: the card's attribute, its type, or none
WHICH = ("first", "second", "both")
SAMPLE = 200


@dataclass
class RuleSpec:
    filter: CardFilter = field(default_factory=CardFilter)
    which: str = "first"
    source: str = "attribute"
    mapping: dict = field(default_factory=dict)    # attribute or type -> star; "star": {None: star}
    # "second" only: a card whose second star would equal its first gets none
    # instead (one star: no choice at summon).


@dataclass
class Plan:
    changes: list = field(default_factory=list)     # (cid, (star1, star2) before, (star1, star2) after)
    chosen: int = 0                                  # cards the filter chose
    skipped: int = 0                                 # chosen, but not monsters or with no rule for them
    errors: list = field(default_factory=list)

    def ok(self) -> bool:
        return not self.errors and bool(self.changes)

    def summary(self) -> str:
        return (f"{self.chosen} cards chosen: {len(self.changes)} change, "
                f"{self.chosen - len(self.changes) - self.skipped} already so, {self.skipped} without a rule")


def _star_for(card, spec: RuleSpec):
    if spec.source == "attribute":
        return spec.mapping.get(card.attribute)
    if spec.source == "type":
        return spec.mapping.get(card.type)
    return spec.mapping.get(None)


def plan(project, spec: RuleSpec, count: int = 15) -> Plan:
    out = Plan()
    if spec.which not in WHICH or spec.source not in SOURCES:
        out.errors.append("choose which star and what picks it")
        return out
    for value in spec.mapping.values():
        if value is not None and not 0 <= value <= count:
            out.errors.append(f"star {value}: the stars are 1 to {count} (0: none)")
            return out
    if spec.filter.empty():
        out.errors.append("choose some cards: an empty filter would change every monster")
        return out
    chosen, unknown = spec.filter.select(project)
    if unknown:
        out.errors.append("not cards: " + ", ".join(unknown[:5]))
        return out
    out.chosen = len(chosen)
    for cid in chosen:
        card = project.cards[cid]
        star = _star_for(card, spec) if card.is_monster() else None
        if star is None:
            out.skipped += 1
            continue
        first, second = card.star1, card.star2
        if spec.which in ("first", "both"):
            first = star
        if spec.which in ("second", "both"):
            second = star
        # As the game has them (stars.c Stars_Normalize): a first star of
        # none leaves the second as the card's one star; both none, no star.
        first, second = guardian_stars.normalized(first, second)
        if (first, second) != (card.star1, card.star2):
            out.changes.append((cid, (card.star1, card.star2), (first, second)))
    return out


@dataclass
class Batch:
    project: object
    cards: dict = field(default_factory=dict)       # cid -> (before, after)
    description: str = ""


def apply(project, the_plan: Plan, description: str = "") -> Batch:
    if the_plan.errors:
        raise ValueError("; ".join(the_plan.errors))
    batch = Batch(project, description=description)
    for cid, before, after in the_plan.changes:
        card = project.cards[cid].copy()
        card.star1, card.star2 = after
        project.cards[cid] = card
        batch.cards[cid] = (before, after)
    return batch


def undo(project, batch: Batch) -> tuple:
    """(cards put back, cards edited since and left as they are)."""
    if batch.project is not project:
        raise ValueError("the batch was made on another mod")
    restored = skipped = 0
    for cid, (before, after) in batch.cards.items():
        card = project.cards.get(cid)
        if card is None or (card.star1, card.star2) != after:
            skipped += 1
            continue
        card = card.copy()
        card.star1, card.star2 = before
        project.cards[cid] = card
        restored += 1
    return restored, skipped
