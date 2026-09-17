"""Minimal builders for records the constraint tests need.

Only fields the tests care about are parameterised; everything else gets a
plausible constant so a test reads as the one thing it is checking.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import (
    AppUser,
    Asset,
    CaptureRecipe,
    ChecklistItem,
    Evidence,
    Project,
    Requirement,
    SourceDocument,
)
from app.models.enums import (
    ChecklistItemState,
    Criticality,
    DocumentType,
    EvidenceStatus,
    MediaType,
    ReconciliationStatus,
    RequirementStatus,
    UserRole,
    VerificationMethod,
)

SHA256_OF_EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def make_project(db: Session, name: str = "DC-07 Pilot") -> Project:
    project = Project(name=name, cxalloy_project_id="CX-PROJ-1")
    db.add(project)
    db.flush()
    return project


def make_user(db: Session, role: UserRole = UserRole.REVIEWER) -> AppUser:
    user = AppUser(
        oidc_subject=f"sso|{uuid.uuid4()}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        display_name="Test Person",
        roles=[role],
    )
    db.add(user)
    db.flush()
    return user


def make_document(db: Session, project: Project) -> SourceDocument:
    doc = SourceDocument(
        project_id=project.id,
        doc_type=DocumentType.SPEC_SECTION,
        title="26 05 00 Common Work Results for Electrical",
    )
    db.add(doc)
    db.flush()
    return doc


def make_requirement(
    db: Session,
    project: Project,
    document: SourceDocument,
    *,
    criticality: Criticality = Criticality.QUALITY,
    status: RequirementStatus = RequirementStatus.APPROVED,
    why_it_matters: str = "A mislabelled panel sends the next person to the wrong board.",
    evidence_spec: list[dict[str, str]] | None = None,
) -> Requirement:
    requirement = Requirement(
        project_id=project.id,
        applies_to_equipment_class=["switchboard"],
        applies_to_system="normal_power",
        applies_to_location_type="electrical_room",
        statement="The equipment nameplate shows the panel tag.",
        verification_method=VerificationMethod.VISUAL,
        evidence_spec=(
            evidence_spec
            if evidence_spec is not None
            else [{"capture_recipe_id": str(uuid.uuid4()), "version": "1.0.0"}]
        ),
        pass_criteria={"kind": "presence", "expected": "present", "subject": "nameplate"},
        criticality=criticality,
        source_doc_id=document.id,
        source_clause="26 05 53 - 2.1.A",
        source_page=3,
        precedence_rank=0,
        why_it_matters=why_it_matters,
        status=status,
        ruleset_version="1.0.0",
    )
    db.add(requirement)
    db.flush()
    return requirement


def make_asset(db: Session, project: Project, tag: str = "SWBD-101") -> Asset:
    asset = Asset(
        project_id=project.id,
        tag=tag,
        equipment_class="switchboard",
        system="normal power",
        location_room="Electrical Room 1-04",
        location_type="electrical_room",
        reconciliation_status=ReconciliationStatus.HUMAN_CONFIRMED,
    )
    db.add(asset)
    db.flush()
    return asset


def make_checklist_item(
    db: Session,
    asset: Asset,
    requirement: Requirement,
    *,
    state: ChecklistItemState = ChecklistItemState.OPEN,
    ruleset_version: str = "1.0.0",
    **overrides: object,
) -> ChecklistItem:
    item = ChecklistItem(
        asset_id=asset.id,
        requirement_id=requirement.id,
        ruleset_version=ruleset_version,
        state=state,
        **overrides,
    )
    db.add(item)
    db.flush()
    return item


def make_capture_recipe(db: Session, slug: str = "visual_presence") -> CaptureRecipe:
    recipe = CaptureRecipe(
        slug=slug,
        version="1.0.0",
        verification_method=VerificationMethod.VISUAL,
        steps=[{"instruction": "Wide shot of the panel", "gate_check": "sharpness_floor"}],
        disqualifiers=["glare", "obstruction"],
    )
    db.add(recipe)
    db.flush()
    return recipe


def make_evidence(
    db: Session,
    item: ChecklistItem,
    recipe: CaptureRecipe,
    user: AppUser,
    *,
    client_id: uuid.UUID | None = None,
) -> Evidence:
    evidence = Evidence(
        client_id=client_id or uuid.uuid4(),
        checklist_item_id=item.id,
        capture_recipe_id=recipe.id,
        capture_recipe_version=recipe.version,
        step_index=0,
        media_type=MediaType.PHOTO,
        storage_key=f"projects/dc-07/evidence/{uuid.uuid4()}.jpg",
        content_hash=SHA256_OF_EMPTY,
        byte_size=2841177,
        mime_type="image/jpeg",
        captured_at=datetime(2026, 9, 15, 10, 31, 8, tzinfo=UTC),
        received_at=datetime(2026, 9, 15, 15, 47, 52, tzinfo=UTC),
        captured_by=user.id,
        device_metadata={"model": "Pixel 8", "os_version": "Android 15", "app_version": "0.1.0"},
        gate_results=[],
        status=EvidenceStatus.STORED,
    )
    db.add(evidence)
    db.flush()
    return evidence
