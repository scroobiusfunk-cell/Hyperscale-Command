"""Rendering rulings into an import package.

ADR-0001: the CxAlloy API is read only, so a ruling reaches the system of record
when a person imports a file. This builds that file.

Nothing can write to CxAlloy — not the API, and not an importer. A person opens
CxAlloy and types the results in, so the package is a worklist for a human doing
repetitive data entry. The spreadsheet is the part they actually use; the CSVs
are kept because they are deterministic and hashable, and because a machine path
may exist one day.

Three properties the ADR asks for, all tested:

- **Deterministic.** The same set of rulings renders byte-for-byte the same
  manifest, so a re-import is recognisable as a duplicate rather than landing
  twice. Nothing generation-time goes inside the compared content.
- **Failures are separate.** A passed item sitting undelivered is administrative
  lag; a failed one is a defect nobody has been told to fix. They go in their
  own file so the person importing cannot miss them.
- **Delivery is acknowledged by a person.** Writing the file is not delivery.
  The platform cannot confirm on a human's behalf that anything reached CxAlloy.
"""

from __future__ import annotations

import csv
import hashlib
import io
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cxalloy.worklist import build_workbook
from app.logging import get_logger
from app.models import (
    AppUser,
    Asset,
    ChecklistItem,
    Evidence,
    ExportStatus,
    Requirement,
    ResultsExport,
    Ruling,
)
from app.models.enums import ChecklistItemState, CxAlloyDeliveryState
from app.storage import ObjectStorage, StorageError

log = get_logger(__name__)

#: States whose result belongs in CxAlloy.
DELIVERABLE_STATES = frozenset(
    {
        ChecklistItemState.REVIEWER_PASSED,
        ChecklistItemState.REVIEWER_FAILED,
        ChecklistItemState.AUTO_CLEARED,
    }
)

WORKLIST_NAME = "enter_these_in_cxalloy.xlsx"
MANIFEST_NAME = "checklist_results.csv"
FAILURES_NAME = "failures_open_an_issue.csv"
README_NAME = "README.txt"

MANIFEST_COLUMNS = (
    "export_key",
    "cxalloy_id",
    "asset_tag",
    "requirement_statement",
    "result",
    "ruled_at",
    "ruled_by",
    "note",
    "evidence_files",
)

FAILURE_COLUMNS = (
    "export_key",
    "cxalloy_id",
    "asset_tag",
    "requirement_statement",
    "why_it_matters",
    "ruled_at",
    "ruled_by",
    "note",
    "evidence_files",
)


class ExportError(RuntimeError):
    """The package could not be built."""


@dataclass(frozen=True)
class DeliveryStatus:
    """What is waiting to reach the system of record."""

    pending_export: int = 0
    exported_not_confirmed: int = 0
    undelivered_failures: int = 0
    """Counted separately: a failed item nobody has been told about is a defect."""

    @property
    def undelivered(self) -> int:
        return self.pending_export + self.exported_not_confirmed


@dataclass(frozen=True)
class _Row:
    item: ChecklistItem
    asset: Asset
    requirement: Requirement
    ruling: Ruling | None
    evidence: list[Evidence]

    @property
    def export_key(self) -> str:
        """Stable per ruling, so the importer can spot a duplicate.

        Keyed on the ruling rather than the item: a correction is a new ruling
        and has to be importable as a new row, not silently collapse onto the
        one it replaced.
        """
        if self.ruling is not None:
            return f"{self.item.id}:{self.ruling.id}"
        resolved = self.item.resolved_at.isoformat() if self.item.resolved_at else "unresolved"
        return f"{self.item.id}:{resolved}"

    @property
    def failed(self) -> bool:
        return self.item.state is ChecklistItemState.REVIEWER_FAILED


def _gather(session: Session, project_id: uuid.UUID) -> list[_Row]:
    items = list(
        session.execute(
            select(ChecklistItem)
            .join(Asset, Asset.id == ChecklistItem.asset_id)
            .where(
                Asset.project_id == project_id,
                ChecklistItem.state.in_(DELIVERABLE_STATES),
                ChecklistItem.cxalloy_delivery_state.in_(
                    (CxAlloyDeliveryState.NOT_APPLICABLE, CxAlloyDeliveryState.PENDING_EXPORT)
                ),
            )
        )
        .scalars()
        .all()
    )
    if not items:
        return []

    assets = {
        a.id: a
        for a in session.execute(select(Asset).where(Asset.id.in_({i.asset_id for i in items})))
        .scalars()
        .all()
    }
    requirements = {
        (r.id, r.ruleset_version): r
        for r in session.execute(
            select(Requirement).where(Requirement.id.in_({i.requirement_id for i in items}))
        )
        .scalars()
        .all()
    }
    rulings: dict[uuid.UUID, Ruling] = {}
    for ruling in (
        session.execute(
            select(Ruling)
            .where(Ruling.checklist_item_id.in_({i.id for i in items}))
            .order_by(Ruling.created_at)
        )
        .scalars()
        .all()
    ):
        rulings[ruling.checklist_item_id] = ruling  # newest wins

    evidence_by_item: dict[uuid.UUID, list[Evidence]] = {}
    for evidence in (
        session.execute(
            select(Evidence)
            .where(Evidence.checklist_item_id.in_({i.id for i in items}))
            .order_by(Evidence.step_index, Evidence.client_id)
        )
        .scalars()
        .all()
    ):
        evidence_by_item.setdefault(evidence.checklist_item_id, []).append(evidence)

    rows = [
        _Row(
            item=item,
            asset=assets[item.asset_id],
            requirement=requirements[(item.requirement_id, item.ruleset_version)],
            ruling=rulings.get(item.id),
            evidence=evidence_by_item.get(item.id, []),
        )
        for item in items
        if (item.requirement_id, item.ruleset_version) in requirements
    ]
    # Stable order, so two renders of the same rulings match byte for byte.
    return sorted(rows, key=lambda r: r.export_key)


def _photo_path(row: _Row, evidence: Evidence) -> str:
    suffix = evidence.storage_key.rsplit(".", 1)[-1] if "." in evidence.storage_key else "bin"
    name = f"{evidence.step_index:02d}_{evidence.client_id}.{suffix}"
    return f"photos/{row.asset.tag}/{row.item.id}/{name}"


def _render_csv(columns: tuple[str, ...], rows: list[list[str]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue()


def _manifest_rows(rows: list[_Row], *, failures_only: bool) -> list[list[str]]:
    out: list[list[str]] = []
    for row in rows:
        if failures_only and not row.failed:
            continue
        files = " | ".join(_photo_path(row, e) for e in row.evidence)
        ruled_at = row.item.resolved_at.isoformat() if row.item.resolved_at else ""
        ruled_by = str(row.item.resolved_by) if row.item.resolved_by else ""
        note = (row.ruling.note if row.ruling and row.ruling.note else "") or ""
        if failures_only:
            out.append(
                [
                    row.export_key,
                    row.asset.cxalloy_id or "",
                    row.asset.tag,
                    row.requirement.statement,
                    row.requirement.why_it_matters,
                    ruled_at,
                    ruled_by,
                    note,
                    files,
                ]
            )
        else:
            out.append(
                [
                    row.export_key,
                    row.asset.cxalloy_id or "",
                    row.asset.tag,
                    row.requirement.statement,
                    row.item.state.value,
                    ruled_at,
                    ruled_by,
                    note,
                    files,
                ]
            )
    return out


README_TEXT = f"""\
Field Inspection Engine — results to enter in CxAlloy
====================================================

Start with {WORKLIST_NAME}. That is the worklist: one row per ruling, in CxAlloy
id order, with a Done column to keep your place.

Nothing in this package reaches CxAlloy on its own. This platform's access to
CxAlloy is read only and cannot be automated, so these results have to be
entered by hand.

The Failures sheet is the items that failed, pulled out on their own. Each one
needs an issue raising against it. They are in the Results sheet too.

photos/ holds the evidence, named by asset tag, checklist item and capture step.
The Evidence files column on each row says which belong to it.

{MANIFEST_NAME} and {FAILURES_NAME} are the same data as plain CSV, for anything
that wants to read it mechanically.

Each row has an export_key. It is stable, so if this package is produced twice
you can tell a repeat from something new.

When you have finished, confirm delivery in the reviewer console. Until somebody
does, these rulings count as not yet in CxAlloy, and the undelivered count keeps
climbing whether or not the work was actually done.
"""


def build_export(
    session: Session,
    storage: ObjectStorage,
    *,
    project_id: uuid.UUID,
    bucket: str,
) -> ResultsExport:
    """Render every undelivered ruling into one package.

    An item already exported is not included again, so running this twice in a
    row produces an empty second package rather than a duplicate of the first.
    """
    rows = _gather(session, project_id)

    export = ResultsExport(
        project_id=project_id,
        status=ExportStatus.PENDING,
        item_count=len(rows),
        failure_count=sum(1 for r in rows if r.failed),
    )
    session.add(export)
    session.flush()

    if not rows:
        export.status = ExportStatus.RENDERED
        export.rendered_at = datetime.now(UTC)
        export.content_hash = hashlib.sha256(b"").hexdigest()
        session.flush()
        return export

    manifest = _render_csv(MANIFEST_COLUMNS, _manifest_rows(rows, failures_only=False))
    failures = _render_csv(FAILURE_COLUMNS, _manifest_rows(rows, failures_only=True))

    # The hash covers the manifest only. The zip's own bytes carry timestamps
    # and compression details that would make two identical exports look
    # different, which is the opposite of what the key is for.
    content_hash = hashlib.sha256(manifest.encode("utf-8")).hexdigest()

    export.attempts += 1
    try:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(WORKLIST_NAME, build_workbook(rows, _photo_path))
            archive.writestr(MANIFEST_NAME, manifest)
            archive.writestr(FAILURES_NAME, failures)
            archive.writestr(README_NAME, README_TEXT)
            for row in rows:
                for evidence in row.evidence:
                    try:
                        archive.writestr(
                            _photo_path(row, evidence), storage.get(bucket, evidence.storage_key)
                        )
                    except StorageError:
                        # A missing photo must not lose the ruling. The row
                        # still goes in; the file is named and absent, which is
                        # visible to whoever imports it. See OPEN_QUESTIONS Q21.
                        log.warning(
                            "export.evidence_missing",
                            evidence_id=str(evidence.id),
                            storage_key=evidence.storage_key,
                        )

        key = f"projects/{project_id}/exports/{export.id}.zip"
        export.storage_key = storage.put(bucket, key, buffer.getvalue(), "application/zip")
    except Exception as exc:
        export.status = ExportStatus.FAILED
        export.last_error = str(exc)
        session.flush()
        log.error("export.failed", export_id=str(export.id), error=str(exc))
        raise ExportError(str(exc)) from exc

    now = datetime.now(UTC)
    export.status = ExportStatus.RENDERED
    export.rendered_at = now
    export.content_hash = content_hash

    for row in rows:
        row.item.cxalloy_delivery_state = CxAlloyDeliveryState.EXPORTED
        row.item.export_key = row.export_key
        row.item.cxalloy_exported_at = now

    session.flush()
    log.info(
        "export.rendered",
        export_id=str(export.id),
        project_id=str(project_id),
        items=export.item_count,
        failures=export.failure_count,
        content_hash=content_hash,
    )
    return export


def confirm_delivery(
    session: Session, export_id: uuid.UUID, *, confirmed_by: uuid.UUID
) -> ResultsExport:
    """A person says the import is done.

    This is the only thing that clears the undelivered count. Rendering a file
    is not delivery, and the platform cannot confirm on a human's behalf that
    anything reached the system of record.
    """
    export = session.get(ResultsExport, export_id)
    if export is None:
        raise ExportError(f"No export {export_id}.")
    if export.status is not ExportStatus.RENDERED:
        raise ExportError(f"That export is {export.status.value}, not rendered.")

    user = session.get(AppUser, confirmed_by)
    if user is None or not user.is_active:
        raise ExportError("No such active user.")

    now = datetime.now(UTC)
    export.status = ExportStatus.DELIVERY_CONFIRMED
    export.confirmed_by = confirmed_by
    export.confirmed_at = now

    items = list(
        session.execute(
            select(ChecklistItem)
            .join(Asset, Asset.id == ChecklistItem.asset_id)
            .where(
                Asset.project_id == export.project_id,
                ChecklistItem.cxalloy_delivery_state == CxAlloyDeliveryState.EXPORTED,
                ChecklistItem.cxalloy_exported_at == export.rendered_at,
            )
        )
        .scalars()
        .all()
    )
    for item in items:
        item.cxalloy_delivery_state = CxAlloyDeliveryState.DELIVERY_CONFIRMED
        item.cxalloy_delivery_confirmed_at = now
        item.cxalloy_delivery_confirmed_by = confirmed_by

    session.flush()
    log.info(
        "export.delivery_confirmed",
        export_id=str(export_id),
        items=len(items),
        confirmed_by=str(confirmed_by),
    )
    return export


def delivery_status(session: Session, project_id: uuid.UUID) -> DeliveryStatus:
    """Tracked from day one, alongside reconciliation queue size.

    Both measure the same thing from different ends: the platform drifting out
    of step with the physical project.
    """
    items = list(
        session.execute(
            select(ChecklistItem)
            .join(Asset, Asset.id == ChecklistItem.asset_id)
            .where(
                Asset.project_id == project_id,
                ChecklistItem.state.in_(DELIVERABLE_STATES),
            )
        )
        .scalars()
        .all()
    )

    pending = sum(
        1
        for i in items
        if i.cxalloy_delivery_state
        in (CxAlloyDeliveryState.NOT_APPLICABLE, CxAlloyDeliveryState.PENDING_EXPORT)
    )
    exported = sum(1 for i in items if i.cxalloy_delivery_state is CxAlloyDeliveryState.EXPORTED)
    failures = sum(
        1
        for i in items
        if i.state is ChecklistItemState.REVIEWER_FAILED
        and i.cxalloy_delivery_state is not CxAlloyDeliveryState.DELIVERY_CONFIRMED
    )
    return DeliveryStatus(
        pending_export=pending,
        exported_not_confirmed=exported,
        undelivered_failures=failures,
    )
