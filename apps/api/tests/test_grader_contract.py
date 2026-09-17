"""GraderResult's output contract, enforced at the storage layer.

Nothing writes a GraderResult in Phase 1. These tests exist so the contract is
already nailed down when the first grader arrives, rather than being negotiated
against a grader that is already producing values.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import GraderResult
from app.models.enums import GraderVerdict, UserRole
from tests import factories as f


@pytest.fixture
def checklist_item_id(db: Session) -> uuid.UUID:
    project = f.make_project(db)
    document = f.make_document(db, project)
    asset = f.make_asset(db, project)
    requirement = f.make_requirement(db, project, document)
    f.make_user(db, UserRole.TECH)
    return f.make_checklist_item(db, asset, requirement).id


def _result(checklist_item_id: uuid.UUID, **overrides: Any) -> GraderResult:
    fields = {
        "checklist_item_id": checklist_item_id,
        "verdict": GraderVerdict.PASS,
        "confidence": 0.92,
        "evidence_used": [{"evidence_id": "00000000-0000-4000-8000-000000000000", "regions": []}],
        "observed_value": {"text": "SWBD-101"},
        "expected_value": {"text": "SWBD-101"},
        "explanation": "The tag on the nameplate matches the schedule.",
        "grader_id": "ocr_compare",
        "grader_version": "1.0.0",
        "model_version": None,
    }
    fields.update(overrides)
    return GraderResult(**fields)


def test_a_grader_that_cannot_tell_may_not_also_be_confident(
    db: Session, checklist_item_id: uuid.UUID
) -> None:
    """The confident wrong pass is the failure mode this system designs against."""
    db.add(
        _result(
            checklist_item_id,
            verdict=GraderVerdict.INSUFFICIENT_EVIDENCE,
            confidence=0.95,
        )
    )
    with pytest.raises(IntegrityError, match="ck_grader_result_insufficient_is_not_confident"):
        db.flush()


def test_insufficient_evidence_with_low_confidence_is_fine(
    db: Session, checklist_item_id: uuid.UUID
) -> None:
    result = _result(
        checklist_item_id, verdict=GraderVerdict.INSUFFICIENT_EVIDENCE, confidence=0.31
    )
    db.add(result)
    db.flush()
    assert result.verdict is GraderVerdict.INSUFFICIENT_EVIDENCE


def test_a_verdict_must_cite_evidence(db: Session, checklist_item_id: uuid.UUID) -> None:
    db.add(_result(checklist_item_id, evidence_used=[]))
    with pytest.raises(IntegrityError, match="ck_grader_result_cites_evidence"):
        db.flush()


@pytest.mark.parametrize("confidence", [-0.1, 1.5])
def test_confidence_stays_within_zero_and_one(
    db: Session, checklist_item_id: uuid.UUID, confidence: float
) -> None:
    db.add(_result(checklist_item_id, confidence=confidence))
    with pytest.raises(IntegrityError, match="ck_grader_result_confidence_range"):
        db.flush()
