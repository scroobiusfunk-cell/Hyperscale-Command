"""Worked examples: what a correct install looks like, and what a wrong one does.

A requirement in words tells a learner what to verify. It does not tell them
what it looks like, and that gap is most of what a green inspector is missing.

Two things about the design are deliberate.

**A caption is required.** An image with no caption is a photograph; with one it
is a lesson. "Note the plate is seated flush — a proud plate is the common
miss" teaches something a bare picture does not, and the database refuses a
blank one.

**Wrong examples matter more than right ones.** Anybody can recognise a missing
part. What a learner walks past is the near-miss: fitted but not seated, legible
close up and unreadable from standing position. So examples are stored in two
kinds and the field app shows both.

Examples key on `item_type` — the same grouping used for calibration and for
agreement — so they follow the kind of check rather than one asset, and survive
a new rule-set version. The best source is usually the project's own work, which
is why a reviewer can promote a capture they have just ruled on into a reference
with one action.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models import AppUser, Asset, ChecklistItem, Evidence, ReferenceImage, Requirement
from app.models.enums import ReferenceKind, UserRole
from app.requirements_compiler.grouping import item_type_of
from app.storage import ObjectStorage, StorageError

log = get_logger(__name__)

MIN_CAPTION_CHARS = 8


class ReferenceRejectedError(Exception):
    """The example cannot be stored as asked."""


def reference_storage_key(reference_id: uuid.UUID) -> str:
    return f"reference/{reference_id}"


@dataclass(frozen=True)
class ReferenceView:
    reference_image_id: uuid.UUID
    kind: ReferenceKind
    caption: str
    mime_type: str
    display_order: int


def _require_curator(session: Session, user_id: uuid.UUID) -> AppUser:
    user = session.get(AppUser, user_id)
    if user is None or not user.is_active:
        raise ReferenceRejectedError("No such active user.")
    allowed = {UserRole.REVIEWER, UserRole.CURATOR, UserRole.ADMIN}
    if not (allowed & set(user.roles)):
        raise ReferenceRejectedError(f"{user.display_name} cannot add teaching material.")
    return user


def add_reference(
    session: Session,
    storage: ObjectStorage,
    bucket: str,
    *,
    project_id: uuid.UUID,
    item_type: str,
    kind: ReferenceKind,
    caption: str,
    data: bytes,
    mime_type: str,
    added_by: uuid.UUID,
    display_order: int = 0,
    sourced_from_evidence_id: uuid.UUID | None = None,
) -> ReferenceImage:
    """Store one worked example. Only a reviewer, curator or admin may."""
    user = _require_curator(session, added_by)

    cleaned = caption.strip()
    if len(cleaned) < MIN_CAPTION_CHARS:
        raise ReferenceRejectedError(
            "Say what to notice in this one. An example with no caption is just a photograph."
        )
    if not data:
        raise ReferenceRejectedError("The upload was empty.")

    row = ReferenceImage(
        project_id=project_id,
        item_type=item_type,
        kind=kind,
        caption=cleaned,
        storage_key="",
        content_hash=hashlib.sha256(data).hexdigest(),
        byte_size=len(data),
        mime_type=mime_type,
        display_order=display_order,
        sourced_from_evidence_id=sourced_from_evidence_id,
        added_by=user.id,
    )
    session.add(row)
    session.flush()

    row.storage_key = reference_storage_key(row.id)
    storage.put(bucket, row.storage_key, data, mime_type)
    session.flush()

    log.info(
        "reference.added",
        reference_image_id=str(row.id),
        item_type=item_type,
        kind=kind.value,
        from_evidence=str(sourced_from_evidence_id) if sourced_from_evidence_id else None,
    )
    return row


def promote_evidence(
    session: Session,
    storage: ObjectStorage,
    evidence_bucket: str,
    reference_bucket: str,
    *,
    evidence_id: uuid.UUID,
    kind: ReferenceKind,
    caption: str,
    added_by: uuid.UUID,
    display_order: int = 0,
) -> ReferenceImage:
    """Turn a real capture into teaching material.

    The best example of what good looks like on this job is usually a photograph
    somebody on this job already took, of this make of equipment, in this
    building. The project and the kind of check are read from the evidence
    rather than passed in, so an example cannot be filed against the wrong one.

    The bytes are copied rather than referenced: retiring or superseding the
    evidence later must not blank the lesson.
    """
    evidence = session.get(Evidence, evidence_id)
    if evidence is None:
        raise ReferenceRejectedError("No such evidence.")

    item = session.get(ChecklistItem, evidence.checklist_item_id)
    asset = None if item is None else session.get(Asset, item.asset_id)
    requirement = (
        None
        if item is None
        else session.get(Requirement, (item.requirement_id, item.ruleset_version))
    )
    if item is None or asset is None or requirement is None:
        raise ReferenceRejectedError("That evidence is missing its asset or requirement.")

    try:
        data = storage.get(evidence_bucket, evidence.storage_key)
    except StorageError as exc:
        raise ReferenceRejectedError("That photo has not been uploaded yet.") from exc

    return add_reference(
        session,
        storage,
        reference_bucket,
        project_id=asset.project_id,
        item_type=item_type_of(requirement),
        kind=kind,
        caption=caption,
        data=data,
        mime_type=evidence.mime_type,
        added_by=added_by,
        display_order=display_order,
        sourced_from_evidence_id=evidence.id,
    )


def references_for(
    session: Session, *, project_id: uuid.UUID, item_types: frozenset[str]
) -> dict[str, list[ReferenceView]]:
    """Every active example for these kinds of check, good first then wrong."""
    if not item_types:
        return {}
    rows = (
        session.execute(
            select(ReferenceImage)
            .where(
                ReferenceImage.project_id == project_id,
                ReferenceImage.item_type.in_(item_types),
                ReferenceImage.is_active.is_(True),
            )
            .order_by(ReferenceImage.item_type, ReferenceImage.display_order, ReferenceImage.id)
        )
        .scalars()
        .all()
    )
    out: dict[str, list[ReferenceView]] = {}
    for row in rows:
        out.setdefault(row.item_type, []).append(
            ReferenceView(
                reference_image_id=row.id,
                kind=row.kind,
                caption=row.caption,
                mime_type=row.mime_type,
                display_order=row.display_order,
            )
        )
    for views in out.values():
        views.sort(key=lambda v: (v.kind is not ReferenceKind.GOOD, v.display_order))
    return out
