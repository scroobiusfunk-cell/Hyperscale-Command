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
from app.models import Asset, ChecklistItem, Evidence, Prediction, Requirement, Ruling
from app.models.enums import ChecklistItemState, Criticality, PredictedVerdict, RulingVerdict
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


# A recapture judges the photograph, not the installation, so it can neither
# agree nor disagree with a call about whether the equipment is right.
_COMPARABLE = {RulingVerdict.PASS: PredictedVerdict.PASS, RulingVerdict.FAIL: PredictedVerdict.FAIL}


@dataclass(frozen=True)
class Agreement:
    """How often a learner's own call matched the senior's, per kind of check.

    This is the number the whole teaching claim rests on, so what it excludes
    matters as much as what it counts:

    - `unsure` is not a wrong answer. It is excluded from the rate and reported
      on its own, because a learner who says "I do not know" is telling the
      truth and should not be scored as if they guessed.
    - A `recapture_requested` ruling is excluded entirely: it is a judgement
      about the photograph.
    - Items with no call, or no ruling yet, are not counted.

    `rate` is None rather than 0.0 when nothing is comparable yet. A rate of
    zero means every call was wrong; no rate means there is nothing to say.
    """

    item_type: str
    compared: int
    agreed: int
    unsure: int
    #: Called it right when the senior failed it — catching real defects.
    caught: int
    #: Called it a pass when the senior failed it. The dangerous direction.
    missed: int
    #: Called it a fail when the senior passed it.
    over_called: int

    @property
    def rate(self) -> float | None:
        return None if self.compared == 0 else self.agreed / self.compared


def agreement(
    session: Session,
    *,
    tech_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
) -> tuple[Agreement, tuple[Agreement, ...]]:
    """Overall agreement and a breakdown by kind of check, most-seen first."""
    query = (
        select(Prediction, Ruling)
        .join(Ruling, Ruling.checklist_item_id == Prediction.checklist_item_id)
        .where(Prediction.predicted_by == tech_id)
    )
    if project_id is not None:
        query = (
            query.join(ChecklistItem, ChecklistItem.id == Prediction.checklist_item_id)
            .join(Asset, Asset.id == ChecklistItem.asset_id)
            .where(Asset.project_id == project_id)
        )

    # A correction is a new ruling; the last one for an item is what stands.
    latest: dict[uuid.UUID, tuple[Prediction, Ruling]] = {}
    for prediction, ruling in session.execute(query.order_by(Ruling.created_at)):
        latest[prediction.checklist_item_id] = (prediction, ruling)

    buckets: dict[str, dict[str, int]] = {}
    for prediction, ruling in latest.values():
        bucket = buckets.setdefault(
            prediction.item_type,
            {"compared": 0, "agreed": 0, "unsure": 0, "caught": 0, "missed": 0, "over": 0},
        )
        expected = _COMPARABLE.get(ruling.verdict)
        if expected is None:
            # A recapture judges the photograph. It cannot agree or disagree
            # with a call about the equipment, and it cannot make an "I do not
            # know" into a data point either.
            continue
        if prediction.verdict is PredictedVerdict.UNSURE:
            bucket["unsure"] += 1
            continue
        bucket["compared"] += 1
        if prediction.verdict is expected:
            bucket["agreed"] += 1
            if expected is PredictedVerdict.FAIL:
                bucket["caught"] += 1
        elif expected is PredictedVerdict.FAIL:
            bucket["missed"] += 1
        else:
            bucket["over"] += 1

    per_type = tuple(
        sorted(
            (
                Agreement(
                    item_type=name,
                    compared=b["compared"],
                    agreed=b["agreed"],
                    unsure=b["unsure"],
                    caught=b["caught"],
                    missed=b["missed"],
                    over_called=b["over"],
                )
                for name, b in buckets.items()
            ),
            key=lambda a: (-(a.compared + a.unsure), a.item_type),
        )
    )
    overall = Agreement(
        item_type="all",
        compared=sum(a.compared for a in per_type),
        agreed=sum(a.agreed for a in per_type),
        unsure=sum(a.unsure for a in per_type),
        caught=sum(a.caught for a in per_type),
        missed=sum(a.missed for a in per_type),
        over_called=sum(a.over_called for a in per_type),
    )
    return overall, per_type
