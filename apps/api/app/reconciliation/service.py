"""Applying a match decision to the database.

Two rules run through everything here:

1. Re-running an import must be safe. Every write is keyed so that reconciling
   the same observation twice produces the same state, not a second alias row
   and a second queue entry.
2. The reconciler never invents an asset. An observation it cannot place goes to
   the queue for a person; creating an asset from an unmatched tag would mean
   the field walks to equipment nobody has confirmed exists.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models import Asset, AssetAlias, ReconciliationQueueItem
from app.models.enums import ReconciliationStatus
from app.models.reconciliation import ReconciliationQueueReason, ReconciliationQueueStatus
from app.reconciliation.matcher import (
    DEFAULT_THRESHOLDS,
    AssetCandidate,
    MatchDecision,
    MatchOutcome,
    MatchThresholds,
    TagObservation,
    decide,
)
from app.reconciliation.normalize import canonical_key, normalize_tag

log = get_logger(__name__)

_QUEUE_REASONS = {
    MatchOutcome.QUEUED_NO_MATCH: ReconciliationQueueReason.NO_MATCH,
    MatchOutcome.QUEUED_LOW_CONFIDENCE: ReconciliationQueueReason.LOW_CONFIDENCE,
    MatchOutcome.QUEUED_AMBIGUOUS: ReconciliationQueueReason.AMBIGUOUS,
}


@dataclass(frozen=True)
class ReconciliationResult:
    decision: MatchDecision
    asset_id: uuid.UUID | None
    queue_item_id: uuid.UUID | None

    @property
    def queued(self) -> bool:
        return self.queue_item_id is not None


def load_candidates(
    session: Session, project_id: uuid.UUID, observation: TagObservation
) -> list[AssetCandidate]:
    """Every asset in the project that could plausibly be the one.

    Narrowed by equipment class when the observation states one, because a class
    mismatch is disqualifying in the matcher anyway. Not narrowed by tag: the
    whole problem is that the tags disagree.
    """
    stmt = select(Asset).where(Asset.project_id == project_id)
    if observation.equipment_class is not None:
        stmt = stmt.where(Asset.equipment_class == observation.equipment_class)

    return [
        AssetCandidate(
            asset_id=asset.id,
            tag=asset.tag,
            equipment_class=asset.equipment_class,
            location_room=asset.location_room,
            known_aliases=tuple(alias.value for alias in asset.aliases),
        )
        for asset in session.execute(stmt).scalars().all()
    ]


def reconcile(
    session: Session,
    project_id: uuid.UUID,
    observation: TagObservation,
    *,
    thresholds: MatchThresholds = DEFAULT_THRESHOLDS,
    prefixes: frozenset[str] = frozenset(),
) -> ReconciliationResult:
    """Resolve one observed tag, writing either an alias or a queue entry."""
    candidates = load_candidates(session, project_id, observation)
    decision = decide(observation, candidates, thresholds=thresholds, prefixes=prefixes)

    log.info(
        "reconciliation.decided",
        project_id=str(project_id),
        raw_tag=observation.raw_tag,
        source=observation.source.value,
        outcome=decision.outcome.value,
        candidates_considered=len(candidates),
        best_score=decision.scored[0].score if decision.scored else None,
    )

    if decision.is_auto_match:
        assert decision.matched_asset_id is not None
        _record_alias(session, decision.matched_asset_id, observation)
        _close_open_queue_items(session, project_id, observation)
        return ReconciliationResult(
            decision=decision, asset_id=decision.matched_asset_id, queue_item_id=None
        )

    queue_item = _enqueue(session, project_id, observation, decision)
    return ReconciliationResult(decision=decision, asset_id=None, queue_item_id=queue_item.id)


def _record_alias(session: Session, asset_id: uuid.UUID, observation: TagObservation) -> None:
    """Attach the observed variant to the asset, once.

    Keyed on (asset, raw value, source) to match the table's unique constraint,
    so a re-import updates nothing rather than failing or duplicating.
    """
    existing = session.execute(
        select(AssetAlias).where(
            AssetAlias.asset_id == asset_id,
            AssetAlias.value == observation.raw_tag,
            AssetAlias.source == observation.source,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return

    session.add(
        AssetAlias(
            asset_id=asset_id,
            value=observation.raw_tag,
            normalized_value=canonical_key(observation.raw_tag),
            source=observation.source,
            first_seen_at=datetime.now(UTC),
        )
    )

    asset = session.get(Asset, asset_id)
    if asset is not None and asset.reconciliation_status is ReconciliationStatus.UNRESOLVED:
        # A machine match never upgrades a human decision, so human_confirmed
        # is left alone.
        asset.reconciliation_status = ReconciliationStatus.AUTO_MATCHED
    session.flush()


def _enqueue(
    session: Session,
    project_id: uuid.UUID,
    observation: TagObservation,
    decision: MatchDecision,
) -> ReconciliationQueueItem:
    """Add to the queue, or refresh the open entry that is already there."""
    normalized = normalize_tag(observation.raw_tag)
    existing = session.execute(
        select(ReconciliationQueueItem).where(
            ReconciliationQueueItem.project_id == project_id,
            ReconciliationQueueItem.normalized_tag == normalized,
            ReconciliationQueueItem.source == observation.source,
            ReconciliationQueueItem.status == ReconciliationQueueStatus.OPEN,
        )
    ).scalar_one_or_none()

    candidates_json = [
        {
            "asset_id": str(scored.asset_id),
            "score": scored.score,
            "tag_score": scored.tag_score,
            "location_agrees": scored.location_agrees,
            "matched_against": scored.matched_against,
        }
        for scored in decision.scored
    ]

    if existing is not None:
        # Later evidence can change why something is stuck; keep one row and
        # let it say the current reason.
        existing.reason = _QUEUE_REASONS[decision.outcome]
        existing.explanation = decision.reason
        existing.candidates = candidates_json
        session.flush()
        return existing

    item = ReconciliationQueueItem(
        project_id=project_id,
        raw_tag=observation.raw_tag,
        normalized_tag=normalized,
        source=observation.source,
        observed_equipment_class=observation.equipment_class,
        observed_location_room=observation.location_room,
        reason=_QUEUE_REASONS[decision.outcome],
        explanation=decision.reason,
        candidates=candidates_json,
        status=ReconciliationQueueStatus.OPEN,
    )
    session.add(item)
    session.flush()
    return item


def _close_open_queue_items(
    session: Session, project_id: uuid.UUID, observation: TagObservation
) -> None:
    """A tag that now matches should not still be sitting in the queue."""
    normalized = normalize_tag(observation.raw_tag)
    open_items = (
        session.execute(
            select(ReconciliationQueueItem).where(
                ReconciliationQueueItem.project_id == project_id,
                ReconciliationQueueItem.normalized_tag == normalized,
                ReconciliationQueueItem.source == observation.source,
                ReconciliationQueueItem.status == ReconciliationQueueStatus.OPEN,
            )
        )
        .scalars()
        .all()
    )
    for item in open_items:
        item.status = ReconciliationQueueStatus.DISMISSED
    if open_items:
        session.flush()


def resolve_queue_item(
    session: Session,
    queue_item_id: uuid.UUID,
    *,
    asset_id: uuid.UUID,
    resolved_by: uuid.UUID,
) -> ReconciliationQueueItem:
    """A person decides. Their decision is recorded as human_confirmed.

    This is the only path that produces human_confirmed, and the only one that
    can override a machine match.
    """
    item = session.get(ReconciliationQueueItem, queue_item_id)
    if item is None:
        raise LookupError(f"No reconciliation queue item {queue_item_id}")

    _record_alias(
        session,
        asset_id,
        TagObservation(
            raw_tag=item.raw_tag,
            source=item.source,
            equipment_class=item.observed_equipment_class,
            location_room=item.observed_location_room,
        ),
    )

    asset = session.get(Asset, asset_id)
    if asset is not None:
        asset.reconciliation_status = ReconciliationStatus.HUMAN_CONFIRMED

    item.status = ReconciliationQueueStatus.RESOLVED
    item.resolved_asset_id = asset_id
    item.resolved_by = resolved_by
    item.resolved_at = datetime.now(UTC)
    session.flush()

    log.info(
        "reconciliation.resolved_by_person",
        queue_item_id=str(queue_item_id),
        asset_id=str(asset_id),
        resolved_by=str(resolved_by),
    )
    return item


def open_queue_size(session: Session, project_id: uuid.UUID) -> int:
    """Tracked from day one: growth here means the field is walking to wrong assets."""
    return len(
        session.execute(
            select(ReconciliationQueueItem.id).where(
                ReconciliationQueueItem.project_id == project_id,
                ReconciliationQueueItem.status == ReconciliationQueueStatus.OPEN,
            )
        )
        .scalars()
        .all()
    )
