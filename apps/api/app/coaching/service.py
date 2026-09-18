"""Closing the teaching loop: what the reviewer said, back to the tech who shot it.

The product is described as "an inspection assistant and a teaching loop". Until
this module the loop was open at the far end. A reviewer ruled on an item and
wrote a note — mandatory on a fail or a recapture — and that note went into the
database and reached nobody. A tech could walk a building for a month and learn
nothing from any of it.

**This is not the Learner Model.** Section 6 of the architecture doc — competency
scores per (tech, item_type), scaffolding fade, spaced repetition, self-clear
unlock — is Phase 3 and none of it is here. There is no score, no threshold, no
state machine, and nothing in this file changes what any tech is allowed to do.
It only shows a person the rulings on their own work. See Q27.

Two orderings matter, and they are not the same:

- *Needs another visit* comes first, because a recapture request is a job, not a
  lesson. A tech who does not know an item was sent back will not go back.
- Then failures, then passes, newest first. The note on a failure is the lesson;
  the note on a pass is why it was right, which is the thing that generalises.

"Your work" means evidence this person captured, not items assigned to them. A
tech who photographs an item somebody else was assigned still took the
photograph, and the ruling on it is still theirs to learn from.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models import Asset, ChecklistItem, Evidence, Requirement, Ruling
from app.models.enums import ChecklistItemState, Criticality, RulingVerdict
from app.models.identity import AppUser

log = get_logger(__name__)

#: A recapture is work to redo; a fail is the lesson; a pass is the confirmation.
_VERDICT_ORDER = {
    RulingVerdict.RECAPTURE_REQUESTED: 0,
    RulingVerdict.FAIL: 1,
    RulingVerdict.PASS: 2,
}


@dataclass(frozen=True)
class Feedback:
    """One ruling on something this tech captured."""

    checklist_item_id: uuid.UUID
    asset_tag: str
    room: str | None
    statement: str
    why_it_matters: str
    criticality: Criticality
    verdict: RulingVerdict
    note: str | None
    reviewer_name: str
    ruled_at: datetime
    #: True when the item is open again and the tech has to go back to it.
    needs_another_visit: bool
    #: A correction supersedes an earlier ruling; both stay readable.
    is_correction: bool
    evidence_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class Tally:
    """A plain count of outcomes. Deliberately not a score.

    No rate, no threshold, nothing gated on it. A competency score compares a
    tech's own call against the ruling, and in Phase 1 the tech never makes a
    call, so there is nothing to compare and any number here would be theatre.
    """

    ruled: int
    passed: int
    failed: int
    recapture_requested: int
    awaiting_review: int


@dataclass(frozen=True)
class MyWork:
    tally: Tally
    feedback: tuple[Feedback, ...]


def my_work(
    session: Session, *, tech_id: uuid.UUID, project_id: uuid.UUID | None = None, limit: int = 100
) -> MyWork:
    """Every ruling on evidence this person captured, most useful first."""
    captured = select(Evidence.checklist_item_id).where(Evidence.captured_by == tech_id)
    if project_id is not None:
        captured = (
            captured.join(ChecklistItem, ChecklistItem.id == Evidence.checklist_item_id)
            .join(Asset, Asset.id == ChecklistItem.asset_id)
            .where(Asset.project_id == project_id)
        )

    item_ids = set(session.execute(captured.distinct()).scalars().all())
    if not item_ids:
        return MyWork(tally=Tally(0, 0, 0, 0, 0), feedback=())

    evidence_by_item: dict[uuid.UUID, list[uuid.UUID]] = {}
    for evidence_id, item_id in session.execute(
        select(Evidence.id, Evidence.checklist_item_id)
        .where(Evidence.captured_by == tech_id, Evidence.checklist_item_id.in_(item_ids))
        .order_by(Evidence.step_index, Evidence.received_at)
    ):
        evidence_by_item.setdefault(item_id, []).append(evidence_id)

    # Rulings oldest first, so the last one written for an item is the one that
    # stands. A correction is a new ruling, never an edit.
    rulings = list(
        session.execute(
            select(Ruling).where(Ruling.checklist_item_id.in_(item_ids)).order_by(Ruling.created_at)
        )
        .scalars()
        .all()
    )
    latest: dict[uuid.UUID, Ruling] = {r.checklist_item_id: r for r in rulings}

    reviewers = {
        u.id: u
        for u in session.execute(
            select(AppUser).where(
                AppUser.id.in_({r.reviewer_id for r in rulings} or {uuid.uuid4()})
            )
        )
        .scalars()
        .all()
    }
    items = {
        i.id: i
        for i in session.execute(select(ChecklistItem).where(ChecklistItem.id.in_(item_ids)))
        .scalars()
        .all()
    }
    assets = {
        a.id: a
        for a in session.execute(
            select(Asset).where(Asset.id.in_({i.asset_id for i in items.values()}))
        )
        .scalars()
        .all()
    }

    entries: list[Feedback] = []
    for item_id, ruling in latest.items():
        item = items.get(item_id)
        if item is None:
            continue
        asset = assets.get(item.asset_id)
        requirement = session.get(Requirement, (item.requirement_id, item.ruleset_version))
        if asset is None or requirement is None:
            continue
        reviewer = reviewers.get(ruling.reviewer_id)
        entries.append(
            Feedback(
                checklist_item_id=item_id,
                asset_tag=asset.tag,
                room=asset.location_room,
                statement=requirement.statement,
                why_it_matters=requirement.why_it_matters,
                criticality=requirement.criticality,
                verdict=ruling.verdict,
                note=ruling.note,
                reviewer_name="A reviewer" if reviewer is None else reviewer.display_name,
                ruled_at=ruling.created_at,
                needs_another_visit=(
                    ruling.verdict is RulingVerdict.RECAPTURE_REQUESTED
                    and item.state is ChecklistItemState.OPEN
                ),
                is_correction=ruling.supersedes is not None,
                evidence_ids=tuple(evidence_by_item.get(item_id, [])),
            )
        )

    entries.sort(key=lambda f: (_VERDICT_ORDER.get(f.verdict, 9), -f.ruled_at.timestamp()))

    awaiting = sum(
        1
        for item_id in item_ids
        if item_id not in latest
        and (items[item_id].state if item_id in items else None)
        in (ChecklistItemState.EVIDENCE_CAPTURED, ChecklistItemState.ROUTED)
    )
    tally = Tally(
        ruled=len(entries),
        passed=sum(1 for f in entries if f.verdict is RulingVerdict.PASS),
        failed=sum(1 for f in entries if f.verdict is RulingVerdict.FAIL),
        recapture_requested=sum(
            1 for f in entries if f.verdict is RulingVerdict.RECAPTURE_REQUESTED
        ),
        awaiting_review=awaiting,
    )

    log.info(
        "coaching.my_work",
        tech_id=str(tech_id),
        ruled=tally.ruled,
        awaiting=tally.awaiting_review,
    )
    return MyWork(tally=tally, feedback=tuple(entries[:limit]))
