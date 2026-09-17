"""Turning open checklist items into a guided walk.

"Turns a set of open checklist items into a guided walk the tech can execute
without knowing what matters."

Two halves. `compile_walk` is pure — it reads and decides, and writes nothing,
so a walk can be previewed without marking anything. `start_walk` is the act of
committing to it, and that is where deferrals are recorded, because "deferred
with the reason recorded, not skipped silently" is a promise about the record,
not about the preview.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.capture.recipes import RECIPES_BY_SLUG, RecipeDefinition, recipe_for_criteria
from app.logging import get_logger
from app.models import Asset, CaptureRecipe, ChecklistItem, Requirement
from app.models.enums import (
    AccessConstraint,
    BlockedReason,
    ChecklistItemState,
    Criticality,
)
from app.requirements_compiler.grouping import normalize_subject

log = get_logger(__name__)

#: Phase 1 shows every tech everything. The learner model fades this in Phase 3;
#: until then a constant beats a stub that pretends to decide.
SCAFFOLD_FULL = "full"

#: Which declared-state answer satisfies which constraint.
_CONSTRAINT_REASONS: dict[AccessConstraint, BlockedReason] = {
    AccessConstraint.REQUIRES_DEENERGIZED: BlockedReason.ENERGIZED,
    AccessConstraint.REQUIRES_LADDER: BlockedReason.TOOL_UNAVAILABLE,
    AccessConstraint.REQUIRES_CONFINED_SPACE_ENTRY: BlockedReason.NO_ACCESS,
}


@dataclass(frozen=True)
class DeclaredState:
    """What the tech says is true at the start of the walk.

    `open_rooms` of None means "everything is open" — the common case on a walk
    nobody has had to think about. An explicit empty set means nothing is open,
    which is a different claim and is treated as one.
    """

    open_rooms: frozenset[str] | None = None
    energized_rooms: frozenset[str] = field(default_factory=frozenset)
    ladder_available: bool = False
    confined_space_permit: bool = False

    def room_is_open(self, room: str | None) -> bool:
        if self.open_rooms is None:
            return True
        if room is None:
            # An asset with no room recorded cannot be matched against a list of
            # open rooms, so it is not assumed reachable.
            return False
        return any(normalize_subject(room) == normalize_subject(o) for o in self.open_rooms)

    def room_is_energized(self, room: str | None) -> bool:
        if room is None:
            return False
        return any(normalize_subject(room) == normalize_subject(e) for e in self.energized_rooms)


@dataclass(frozen=True)
class WalkStep:
    instruction: str
    framing_rule: str
    gate_check: str


@dataclass(frozen=True)
class WalkItem:
    """One checklist item as the tech sees it."""

    checklist_item_id: uuid.UUID
    requirement_id: uuid.UUID
    statement: str
    why_it_matters: str
    criticality: Criticality
    steps: tuple[WalkStep, ...]
    recipe_slug: str
    recipe_version: str
    reference_media_slot: str | None
    disqualifiers: tuple[str, ...]
    scaffold_level: str = SCAFFOLD_FULL

    @property
    def is_safety(self) -> bool:
        return self.criticality is Criticality.SAFETY


@dataclass(frozen=True)
class WalkStop:
    """Everything to do at one asset, in one place, before moving on."""

    asset_id: uuid.UUID
    tag: str
    room: str | None
    grid_ref: str | None
    items: tuple[WalkItem, ...]


@dataclass(frozen=True)
class DeferredItem:
    checklist_item_id: uuid.UUID
    asset_tag: str
    reason: BlockedReason
    note: str


@dataclass(frozen=True)
class Walk:
    stops: tuple[WalkStop, ...] = ()
    deferred: tuple[DeferredItem, ...] = ()
    unroutable: tuple[DeferredItem, ...] = ()
    """Items with no capture recipe for their verification method."""

    @property
    def item_count(self) -> int:
        return sum(len(stop.items) for stop in self.stops)


def _recipe_for(session: Session, requirement: Requirement) -> RecipeDefinition | None:
    """The recipe this requirement points at.

    `evidence_spec` is the requirement's own answer to "what must be captured to
    judge it", so the walk follows it rather than re-deriving one. Falling back
    to derivation would mean a curator could point a requirement at one recipe
    and the tech would be handed another.
    """
    for entry in requirement.evidence_spec or []:
        recipe_id = entry.get("capture_recipe_id")
        if not recipe_id:
            continue
        stored = session.get(CaptureRecipe, uuid.UUID(str(recipe_id)))
        if stored is not None and stored.slug in RECIPES_BY_SLUG:
            return RECIPES_BY_SLUG[stored.slug]

    # Nothing usable on the requirement. Derive one only so the reason reported
    # below distinguishes "no recipe exists for this method" from "this
    # requirement was never pointed at one".
    return recipe_for_criteria(requirement.verification_method, requirement.pass_criteria)


def _unmet_constraints(
    requirement: Requirement, asset: Asset, declared: DeclaredState
) -> list[tuple[AccessConstraint, str]]:
    unmet: list[tuple[AccessConstraint, str]] = []
    for constraint in requirement.access_constraints:
        if constraint is AccessConstraint.REQUIRES_DEENERGIZED and declared.room_is_energized(
            asset.location_room
        ):
            unmet.append(
                (constraint, f"{asset.location_room} is energized and this needs it dead.")
            )
        elif constraint is AccessConstraint.REQUIRES_LADDER and not declared.ladder_available:
            unmet.append((constraint, "This is out of reach and there is no ladder."))
        elif (
            constraint is AccessConstraint.REQUIRES_CONFINED_SPACE_ENTRY
            and not declared.confined_space_permit
        ):
            unmet.append((constraint, "This needs a confined space entry permit."))
    return unmet


def _item_sort_key(item: WalkItem) -> tuple[int, str]:
    # Safety first, so a walk cut short has covered the items that matter most.
    return (0 if item.is_safety else 1, item.statement)


def compile_walk(
    session: Session,
    *,
    project_id: uuid.UUID,
    declared: DeclaredState | None = None,
    room: str | None = None,
    asset_ids: frozenset[uuid.UUID] | None = None,
) -> Walk:
    """Build the walk. Reads only; nothing is recorded until `start_walk`."""
    state = declared or DeclaredState()

    asset_query = select(Asset).where(Asset.project_id == project_id)
    if asset_ids:
        asset_query = asset_query.where(Asset.id.in_(asset_ids))
    elif room is not None:
        asset_query = asset_query.where(Asset.location_room == room)
    assets = {a.id: a for a in session.execute(asset_query).scalars().all()}
    if not assets:
        return Walk()

    items = list(
        session.execute(
            select(ChecklistItem).where(
                ChecklistItem.asset_id.in_(assets.keys()),
                ChecklistItem.state == ChecklistItemState.OPEN,
            )
        )
        .scalars()
        .all()
    )
    if not items:
        return Walk()

    requirements = {
        (r.id, r.ruleset_version): r
        for r in session.execute(
            select(Requirement).where(Requirement.id.in_({i.requirement_id for i in items}))
        )
        .scalars()
        .all()
    }

    by_asset: dict[uuid.UUID, list[WalkItem]] = {}
    deferred: list[DeferredItem] = []
    unroutable: list[DeferredItem] = []

    for item in items:
        asset = assets[item.asset_id]
        requirement = requirements.get((item.requirement_id, item.ruleset_version))
        if requirement is None:
            continue

        if not state.room_is_open(asset.location_room):
            deferred.append(
                DeferredItem(
                    checklist_item_id=item.id,
                    asset_tag=asset.tag,
                    reason=BlockedReason.NO_ACCESS,
                    note=(
                        f"{asset.location_room} was not open at the start of the walk."
                        if asset.location_room
                        else "This asset has no room recorded, so it could not be reached."
                    ),
                )
            )
            continue

        unmet = _unmet_constraints(requirement, asset, state)
        if unmet:
            constraint, note = unmet[0]
            deferred.append(
                DeferredItem(
                    checklist_item_id=item.id,
                    asset_tag=asset.tag,
                    reason=_CONSTRAINT_REASONS[constraint],
                    note=note,
                )
            )
            continue

        recipe = _recipe_for(session, requirement)
        if recipe is None:
            unroutable.append(
                DeferredItem(
                    checklist_item_id=item.id,
                    asset_tag=asset.tag,
                    reason=BlockedReason.OTHER,
                    note=(
                        f"No capture recipe covers a "
                        f"{requirement.verification_method.value} requirement in Phase 1."
                    ),
                )
            )
            continue

        by_asset.setdefault(asset.id, []).append(
            WalkItem(
                checklist_item_id=item.id,
                requirement_id=requirement.id,
                statement=requirement.statement,
                why_it_matters=requirement.why_it_matters,
                criticality=requirement.criticality,
                steps=tuple(
                    WalkStep(
                        instruction=step.instruction,
                        framing_rule=step.framing_rule,
                        gate_check=step.gate_check,
                    )
                    for step in recipe.steps
                ),
                recipe_slug=recipe.slug,
                recipe_version=recipe.version,
                reference_media_slot=recipe.reference_media_slot,
                disqualifiers=recipe.disqualifiers,
            )
        )

    # Sequence by location so the tech walks the building rather than the
    # database. Real route optimisation needs floor geometry nobody has here;
    # room then grid reference then tag is stable and good enough to follow.
    stops = tuple(
        WalkStop(
            asset_id=asset_id,
            tag=assets[asset_id].tag,
            room=assets[asset_id].location_room,
            grid_ref=assets[asset_id].location_grid_ref,
            items=tuple(sorted(by_asset[asset_id], key=_item_sort_key)),
        )
        for asset_id in sorted(
            by_asset,
            key=lambda a: (
                assets[a].location_room or "",
                assets[a].location_grid_ref or "",
                assets[a].tag,
            ),
        )
    )

    return Walk(stops=stops, deferred=tuple(deferred), unroutable=tuple(unroutable))


def start_walk(
    session: Session,
    walk: Walk,
    *,
    assigned_tech: uuid.UUID | None = None,
) -> Walk:
    """Commit to a walk: record the deferrals and assign the items.

    Deferral is recorded on the item rather than left in the plan, because the
    plan is gone as soon as the tech closes the app and the reason is the whole
    point of not skipping silently.
    """
    now = datetime.now(UTC)

    for deferral in (*walk.deferred, *walk.unroutable):
        item = session.get(ChecklistItem, deferral.checklist_item_id)
        if item is None or item.state is not ChecklistItemState.OPEN:
            continue
        item.state = ChecklistItemState.BLOCKED
        item.blocked_reason = deferral.reason
        item.blocked_note = deferral.note
        item.blocked_at = now

    if assigned_tech is not None:
        for stop in walk.stops:
            for walk_item in stop.items:
                item = session.get(ChecklistItem, walk_item.checklist_item_id)
                if item is not None:
                    item.assigned_tech = assigned_tech

    session.flush()
    log.info(
        "walk.started",
        stops=len(walk.stops),
        items=walk.item_count,
        deferred=len(walk.deferred),
        unroutable=len(walk.unroutable),
        assigned_tech=str(assigned_tech) if assigned_tech else None,
    )
    return walk
