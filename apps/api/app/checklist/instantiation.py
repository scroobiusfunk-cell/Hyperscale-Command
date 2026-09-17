"""Creating checklist items, lazily, per area.

"A 1,000-asset building with 40 requirements per class produces tens of
thousands of items; generate them lazily per area as the capture plan needs
them, not all upfront."

Three rules keep this from generating work nobody should do:

1. Only a **published** rule set instantiates. A draft is a curator's working
   copy; generating a walk from it would put unapproved requirements in front of
   a tech.
2. Only **approved** requirements instantiate. Draft, needs_review and retired
   requirements are not things anyone should be checking.
3. **Unresolved assets are skipped.** An asset the reconciler could not match is
   one nobody has confirmed exists as described; sending a tech to it is the
   failure the reconciliation queue is there to prevent. They are counted and
   reported rather than silently dropped.

Running it twice over the same area creates nothing the second time.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models import Asset, ChecklistItem, Requirement, RuleSet, RuleSetStatus
from app.models.enums import ChecklistItemState, ReconciliationStatus, RequirementStatus
from app.requirements_compiler.grouping import normalize_subject

log = get_logger(__name__)


class InstantiationError(RuntimeError):
    """An instantiation that must not happen."""


@dataclass(frozen=True)
class Area:
    """Which assets a walk covers.

    A room is the usual unit. Explicit asset ids exist for the cases a room does
    not describe — a riser, a roof, a handful of panels someone wants re-walked.
    """

    project_id: uuid.UUID
    room: str | None = None
    asset_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)

    def describe(self) -> str:
        if self.room:
            return f"room {self.room}"
        if self.asset_ids:
            return f"{len(self.asset_ids)} named assets"
        return "the whole project"


@dataclass(frozen=True)
class InstantiationReport:
    rule_set_id: uuid.UUID
    area: str
    created: int = 0
    already_present: int = 0
    assets_matched: int = 0
    assets_skipped_unresolved: int = 0
    requirements_considered: int = 0

    @property
    def needs_reconciliation_first(self) -> bool:
        """Whether part of this area could not be walked for want of a confirmed asset."""
        return self.assets_skipped_unresolved > 0


def _applies(requirement: Requirement, asset: Asset) -> bool:
    """Whether this requirement governs this asset.

    Class, system and location type, per the architecture doc. A null system or
    location type on the requirement is a wildcard — it governs every system or
    every location type — which is the one place a missing value widens rather
    than narrows.
    """
    classes = {normalize_subject(c) for c in requirement.applies_to_equipment_class}
    if normalize_subject(asset.equipment_class) not in classes:
        return False

    if requirement.applies_to_system is not None and normalize_subject(
        requirement.applies_to_system
    ) != normalize_subject(asset.system):
        return False

    if requirement.applies_to_location_type is not None:
        if asset.location_type is None:
            return False
        if normalize_subject(requirement.applies_to_location_type) != normalize_subject(
            asset.location_type
        ):
            return False

    return True


def instantiate(session: Session, rule_set_id: uuid.UUID, area: Area) -> InstantiationReport:
    """Create the checklist items for one area, skipping anything already there."""
    rule_set = session.get(RuleSet, rule_set_id)
    if rule_set is None:
        raise InstantiationError(f"No rule set {rule_set_id}.")
    if rule_set.status is not RuleSetStatus.PUBLISHED:
        raise InstantiationError(
            f"Rule set {rule_set.version} is {rule_set.status.value}. Only a published rule "
            "set generates checklist items; a draft is a curator's working copy."
        )

    requirements = list(
        session.execute(
            select(Requirement).where(
                Requirement.rule_set_id == rule_set_id,
                Requirement.status == RequirementStatus.APPROVED,
            )
        )
        .scalars()
        .all()
    )

    asset_query = select(Asset).where(Asset.project_id == area.project_id)
    if area.asset_ids:
        asset_query = asset_query.where(Asset.id.in_(area.asset_ids))
    elif area.room is not None:
        asset_query = asset_query.where(Asset.location_room == area.room)
    assets = list(session.execute(asset_query).scalars().all())

    walkable = [a for a in assets if a.reconciliation_status is not ReconciliationStatus.UNRESOLVED]
    skipped = len(assets) - len(walkable)

    existing: set[tuple[uuid.UUID, uuid.UUID]] = set()
    if walkable:
        existing = {
            (item.asset_id, item.requirement_id)
            for item in session.execute(
                select(ChecklistItem).where(
                    ChecklistItem.ruleset_version == rule_set.version,
                    ChecklistItem.asset_id.in_({a.id for a in walkable}),
                )
            )
            .scalars()
            .all()
        }

    created = 0
    already = 0
    matched_assets: set[uuid.UUID] = set()

    for asset in walkable:
        for requirement in requirements:
            if not _applies(requirement, asset):
                continue
            matched_assets.add(asset.id)
            if (asset.id, requirement.id) in existing:
                already += 1
                continue
            session.add(
                ChecklistItem(
                    asset_id=asset.id,
                    requirement_id=requirement.id,
                    ruleset_version=rule_set.version,
                    state=ChecklistItemState.OPEN,
                )
            )
            created += 1

    session.flush()

    report = InstantiationReport(
        rule_set_id=rule_set_id,
        area=area.describe(),
        created=created,
        already_present=already,
        assets_matched=len(matched_assets),
        assets_skipped_unresolved=skipped,
        requirements_considered=len(requirements),
    )
    log.info(
        "instantiation.completed",
        rule_set_id=str(rule_set_id),
        area=report.area,
        created=report.created,
        already_present=report.already_present,
        assets_matched=report.assets_matched,
        assets_skipped_unresolved=report.assets_skipped_unresolved,
    )
    return report
