"""Worked examples: what good looks like, and what wrong looks like.

The gap these fill is the one a specification cannot: a learner can read
"the label is legible from standing position" and still not know what that looks
like until they have seen it. So the tests care about two things — that an
example always carries a caption, and that the examples reach the device with
the walk, before the learner loses signal.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.capture.recipes import ensure_builtin_recipes
from app.coaching.reference import (
    ReferenceRejectedError,
    add_reference,
    promote_evidence,
    reference_storage_key,
    references_for,
)
from app.config import Environment, Settings
from app.deps import get_session, get_storage
from app.main import create_app
from app.models import (
    AppUser,
    CaptureRecipe,
    ChecklistItem,
    Evidence,
    Project,
    ReferenceImage,
    Requirement,
)
from app.models.enums import ChecklistItemState, ReferenceKind, UserRole
from app.requirements_compiler.grouping import item_type_of
from app.storage import InMemoryStorage
from app.sync.blobs import evidence_storage_key
from tests import factories as f

REFERENCE_BUCKET = "understudy-reference"
EVIDENCE_BUCKET = "understudy-evidence"
PHOTO = b"\xff\xd8\xff\xe0 a picture of a correct install"
CAPTION = "Note the plate is seated flush. A proud plate is the common miss."


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def api(db: Session, storage: InMemoryStorage) -> Iterator[TestClient]:
    app = create_app(Settings(environment=Environment.TEST, auth_dev_identity_enabled=True))
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def project(db: Session) -> Project:
    return f.make_project(db)


@pytest.fixture
def curator(db: Session) -> AppUser:
    return f.make_user(db, UserRole.CURATOR)


@pytest.fixture
def learner(db: Session) -> AppUser:
    return f.make_user(db, UserRole.TECH)


def add(
    db: Session,
    storage: InMemoryStorage,
    project: Project,
    who: AppUser,
    *,
    item_type: str = "fillerplatesarefitted",
    kind: ReferenceKind = ReferenceKind.GOOD,
    caption: str = CAPTION,
    data: bytes = PHOTO,
    display_order: int = 0,
) -> ReferenceImage:
    return add_reference(
        db,
        storage,
        REFERENCE_BUCKET,
        project_id=project.id,
        item_type=item_type,
        kind=kind,
        caption=caption,
        data=data,
        mime_type="image/jpeg",
        added_by=who.id,
        display_order=display_order,
    )


class TestAddingAnExample:
    def test_an_example_is_stored_with_its_bytes(
        self, db: Session, storage: InMemoryStorage, project: Project, curator: AppUser
    ) -> None:
        row = add(db, storage, project, curator)

        assert row.storage_key == reference_storage_key(row.id)
        assert storage.get(REFERENCE_BUCKET, row.storage_key) == PHOTO
        assert row.content_hash == hashlib.sha256(PHOTO).hexdigest()

    def test_a_caption_is_required(
        self, db: Session, storage: InMemoryStorage, project: Project, curator: AppUser
    ) -> None:
        """An example with no caption is a photograph, not a lesson."""
        with pytest.raises(ReferenceRejectedError, match="what to notice"):
            add(db, storage, project, curator, caption="  ")

    def test_a_one_word_caption_is_not_enough(
        self, db: Session, storage: InMemoryStorage, project: Project, curator: AppUser
    ) -> None:
        with pytest.raises(ReferenceRejectedError, match="what to notice"):
            add(db, storage, project, curator, caption="good")

    def test_an_empty_upload_is_refused(
        self, db: Session, storage: InMemoryStorage, project: Project, curator: AppUser
    ) -> None:
        with pytest.raises(ReferenceRejectedError, match="empty"):
            add(db, storage, project, curator, data=b"")

    def test_a_learner_cannot_add_teaching_material(
        self, db: Session, storage: InMemoryStorage, project: Project, learner: AppUser
    ) -> None:
        with pytest.raises(ReferenceRejectedError, match="cannot add teaching material"):
            add(db, storage, project, learner)

    def test_a_reviewer_can(self, db: Session, storage: InMemoryStorage, project: Project) -> None:
        reviewer = f.make_user(db, UserRole.REVIEWER)
        assert add(db, storage, project, reviewer).id is not None


class TestWhatTheLearnerGets:
    def test_good_examples_come_before_wrong_ones(
        self, db: Session, storage: InMemoryStorage, project: Project, curator: AppUser
    ) -> None:
        add(db, storage, project, curator, kind=ReferenceKind.WRONG, caption="Fitted but proud.")
        add(db, storage, project, curator, kind=ReferenceKind.GOOD, caption="Seated flush here.")

        views = references_for(
            db, project_id=project.id, item_types=frozenset({"fillerplatesarefitted"})
        )["fillerplatesarefitted"]

        assert [v.kind for v in views] == [ReferenceKind.GOOD, ReferenceKind.WRONG]

    def test_both_kinds_are_carried(
        self, db: Session, storage: InMemoryStorage, project: Project, curator: AppUser
    ) -> None:
        """The near-miss is the one that teaches; it must not be dropped."""
        add(db, storage, project, curator, kind=ReferenceKind.GOOD)
        add(
            db,
            storage,
            project,
            curator,
            kind=ReferenceKind.WRONG,
            caption="Looks fitted from here; it is not seated.",
        )

        views = references_for(
            db, project_id=project.id, item_types=frozenset({"fillerplatesarefitted"})
        )["fillerplatesarefitted"]
        assert len(views) == 2

    def test_a_retired_example_is_not_served(
        self, db: Session, storage: InMemoryStorage, project: Project, curator: AppUser
    ) -> None:
        row = add(db, storage, project, curator)
        row.is_active = False
        db.flush()

        assert (
            references_for(
                db, project_id=project.id, item_types=frozenset({"fillerplatesarefitted"})
            )
            == {}
        )

    def test_another_project_s_examples_are_not_mine(
        self, db: Session, storage: InMemoryStorage, project: Project, curator: AppUser
    ) -> None:
        add(db, storage, project, curator)
        other = f.make_project(db)

        assert (
            references_for(db, project_id=other.id, item_types=frozenset({"fillerplatesarefitted"}))
            == {}
        )

    def test_asking_for_nothing_returns_nothing(self, db: Session, project: Project) -> None:
        assert references_for(db, project_id=project.id, item_types=frozenset()) == {}


class TestPromotingRealWork:
    def _evidence(
        self, db: Session, storage: InMemoryStorage, project: Project, who: AppUser
    ) -> tuple[Evidence, ChecklistItem]:
        document = f.make_document(db, project)
        rule_set = f.make_rule_set(db, project, f"1.{uuid.uuid4().int % 9999}.0")
        requirement = f.make_requirement(db, project, document, rule_set=rule_set)
        item = f.make_checklist_item(
            db,
            f.make_asset(db, project),
            requirement,
            ruleset_version=rule_set.version,
            state=ChecklistItemState.EVIDENCE_CAPTURED,
        )
        ensure_builtin_recipes(db)
        recipe = db.execute(select(CaptureRecipe).limit(1)).scalars().one()
        evidence = f.make_evidence(db, item, recipe, who)
        evidence.storage_key = evidence_storage_key(evidence.client_id)
        db.flush()
        storage.put(EVIDENCE_BUCKET, evidence.storage_key, PHOTO, "image/jpeg")
        return evidence, item

    def test_a_real_capture_becomes_a_lesson(
        self,
        db: Session,
        storage: InMemoryStorage,
        project: Project,
        curator: AppUser,
        learner: AppUser,
    ) -> None:
        """The best example of good on this job is usually already on this job."""
        evidence, _ = self._evidence(db, storage, project, learner)

        row = promote_evidence(
            db,
            storage,
            EVIDENCE_BUCKET,
            REFERENCE_BUCKET,
            evidence_id=evidence.id,
            kind=ReferenceKind.GOOD,
            caption="Textbook example — whole board readable in one frame.",
            added_by=curator.id,
        )

        assert row.sourced_from_evidence_id == evidence.id
        assert row.project_id == project.id
        assert storage.get(REFERENCE_BUCKET, row.storage_key) == PHOTO

    def test_the_bytes_are_copied_not_referenced(
        self,
        db: Session,
        storage: InMemoryStorage,
        project: Project,
        curator: AppUser,
        learner: AppUser,
    ) -> None:
        """Retiring the evidence later must not blank the lesson."""
        evidence, _ = self._evidence(db, storage, project, learner)
        row = promote_evidence(
            db,
            storage,
            EVIDENCE_BUCKET,
            REFERENCE_BUCKET,
            evidence_id=evidence.id,
            kind=ReferenceKind.GOOD,
            caption="Textbook example of a correct install.",
            added_by=curator.id,
        )

        assert row.storage_key != evidence.storage_key
        assert storage.get(REFERENCE_BUCKET, row.storage_key) == PHOTO

    def test_it_is_filed_under_the_right_kind_of_check(
        self,
        db: Session,
        storage: InMemoryStorage,
        project: Project,
        curator: AppUser,
        learner: AppUser,
    ) -> None:
        evidence, item = self._evidence(db, storage, project, learner)
        requirement = db.get(Requirement, (item.requirement_id, item.ruleset_version))

        row = promote_evidence(
            db,
            storage,
            EVIDENCE_BUCKET,
            REFERENCE_BUCKET,
            evidence_id=evidence.id,
            kind=ReferenceKind.GOOD,
            caption="Textbook example of a correct install.",
            added_by=curator.id,
        )

        assert row.item_type == item_type_of(requirement)

    def test_a_photo_that_never_arrived_cannot_be_promoted(
        self,
        db: Session,
        storage: InMemoryStorage,
        project: Project,
        curator: AppUser,
        learner: AppUser,
    ) -> None:
        evidence, _ = self._evidence(db, storage, project, learner)
        storage.objects.pop((EVIDENCE_BUCKET, evidence.storage_key))

        with pytest.raises(ReferenceRejectedError, match="not been uploaded"):
            promote_evidence(
                db,
                storage,
                EVIDENCE_BUCKET,
                REFERENCE_BUCKET,
                evidence_id=evidence.id,
                kind=ReferenceKind.GOOD,
                caption="Textbook example of a correct install.",
                added_by=curator.id,
            )


class TestOverHttp:
    def test_an_example_uploads_and_serves(
        self, api: TestClient, project: Project, curator: AppUser, learner: AppUser
    ) -> None:
        created = api.post(
            f"/reference/projects/{project.id}/images",
            headers={"X-Dev-User-Id": str(curator.id)},
            data={"item_type": "fillerplatesarefitted", "kind": "good", "caption": CAPTION},
            files={"file": ("good.jpg", PHOTO, "image/jpeg")},
        )
        assert created.status_code == 201, created.text
        image_id = created.json()["reference_image_id"]

        # Teaching material: a learner is meant to look at it.
        served = api.get(
            f"/reference/images/{image_id}", headers={"X-Dev-User-Id": str(learner.id)}
        )
        assert served.status_code == 200
        assert served.content == PHOTO

    def test_a_learner_cannot_upload_one(
        self, api: TestClient, project: Project, learner: AppUser
    ) -> None:
        response = api.post(
            f"/reference/projects/{project.id}/images",
            headers={"X-Dev-User-Id": str(learner.id)},
            data={"item_type": "x", "kind": "good", "caption": CAPTION},
            files={"file": ("good.jpg", PHOTO, "image/jpeg")},
        )
        assert response.status_code == 422
        assert "cannot add teaching material" in response.text

    def test_a_missing_caption_is_refused_over_http(
        self, api: TestClient, project: Project, curator: AppUser
    ) -> None:
        response = api.post(
            f"/reference/projects/{project.id}/images",
            headers={"X-Dev-User-Id": str(curator.id)},
            data={"item_type": "x", "kind": "good", "caption": "  "},
            files={"file": ("good.jpg", PHOTO, "image/jpeg")},
        )
        assert response.status_code == 422

    def test_a_retired_example_stops_being_served(
        self, api: TestClient, project: Project, curator: AppUser
    ) -> None:
        image_id = api.post(
            f"/reference/projects/{project.id}/images",
            headers={"X-Dev-User-Id": str(curator.id)},
            data={"item_type": "x", "kind": "wrong", "caption": CAPTION},
            files={"file": ("wrong.jpg", PHOTO, "image/jpeg")},
        ).json()["reference_image_id"]

        api.post(f"/reference/images/{image_id}/retire", headers={"X-Dev-User-Id": str(curator.id)})

        assert (
            api.get(
                f"/reference/images/{image_id}", headers={"X-Dev-User-Id": str(curator.id)}
            ).status_code
            == 404
        )
