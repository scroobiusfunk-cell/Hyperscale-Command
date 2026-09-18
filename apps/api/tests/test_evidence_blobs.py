"""Evidence bytes, which arrive separately from the event log.

The property under test throughout: an `Evidence` row is `stored` only when the
bytes are genuinely in object storage. Anything else is `pending_upload`. A row
that reads as captured evidence with nothing behind it would show a reviewer an
empty frame and let them clear a safety item on a photograph that does not exist.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.capture.recipes import ensure_builtin_recipes
from app.config import Environment, Settings
from app.deps import get_session, get_storage
from app.main import create_app
from app.models import AppUser, CaptureRecipe, ChecklistItem, Evidence, Project
from app.models.enums import EvidenceStatus, UserRole
from app.storage import InMemoryStorage
from app.sync.blobs import (
    BlobRejectedError,
    confirm_uploads,
    evidence_storage_key,
    store_blob,
)
from app.sync.events import EventEnvelope
from app.sync.replay import sync
from tests import factories as f

BUCKET = "fie-evidence"
PHOTO = b"\xff\xd8\xff\xe0 not really a jpeg, but bytes are bytes"
PHOTO_SHA = hashlib.sha256(PHOTO).hexdigest()


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def settings() -> Settings:
    return Settings(environment=Environment.TEST, auth_dev_identity_enabled=True)


@pytest.fixture
def api(db: Session, storage: InMemoryStorage, settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def project(db: Session) -> Project:
    return f.make_project(db)


@pytest.fixture
def tech(db: Session) -> AppUser:
    return f.make_user(db, UserRole.TECH)


@pytest.fixture
def recipe(db: Session) -> CaptureRecipe:
    ensure_builtin_recipes(db)
    return db.execute(select(CaptureRecipe).limit(1)).scalars().one()


@pytest.fixture
def item(db: Session, project: Project) -> ChecklistItem:
    document = f.make_document(db, project)
    rule_set = f.make_rule_set(db, project, "1.0.0")
    requirement = f.make_requirement(db, project, document, rule_set=rule_set)
    return f.make_checklist_item(db, f.make_asset(db, project), requirement)


def capture_event(
    item: ChecklistItem, recipe: CaptureRecipe, *, client_id: uuid.UUID, sequence: int = 0
) -> dict[str, object]:
    return {
        "event_type": "capture_taken",
        "client_event_id": str(uuid.uuid4()),
        "client_walk_id": str(uuid.uuid4()),
        "sequence": sequence,
        "occurred_at": datetime.now(UTC).isoformat(),
        "checklist_item_id": str(item.id),
        "client_id": str(client_id),
        "capture_recipe_id": str(recipe.id),
        "capture_recipe_version": recipe.version,
        "step_index": 0,
        "media_type": "photo",
        "storage_key": "whatever/the/device/says.jpg",
        "content_hash": PHOTO_SHA,
        "byte_size": len(PHOTO),
        "mime_type": "image/jpeg",
    }


def evidence_for(db: Session, client_id: uuid.UUID) -> Evidence:
    return db.execute(select(Evidence).where(Evidence.client_id == client_id)).scalars().one()


class TestTheEventAlone:
    """An event log entry is a claim about a photograph, not the photograph."""

    def test_a_capture_event_alone_leaves_the_row_pending(
        self, db: Session, tech: AppUser, item: ChecklistItem, recipe: CaptureRecipe
    ) -> None:
        client_id = uuid.uuid4()
        sync(
            db,
            submitted_by=tech.id,
            envelope=EventEnvelope.model_validate(
                {"events": [capture_event(item, recipe, client_id=client_id)]}
            ),
        )
        assert evidence_for(db, client_id).status is EvidenceStatus.PENDING_UPLOAD

    def test_the_device_does_not_choose_where_its_bytes_go(
        self, db: Session, tech: AppUser, item: ChecklistItem, recipe: CaptureRecipe
    ) -> None:
        """A device that could name its own key could overwrite another project."""
        client_id = uuid.uuid4()
        sync(
            db,
            submitted_by=tech.id,
            envelope=EventEnvelope.model_validate(
                {"events": [capture_event(item, recipe, client_id=client_id)]}
            ),
        )
        row = evidence_for(db, client_id)
        assert row.storage_key == evidence_storage_key(client_id)
        assert "whatever/the/device/says" not in row.storage_key


class TestUploadingTheBytes:
    def test_bytes_after_the_event_promote_the_row(
        self,
        db: Session,
        storage: InMemoryStorage,
        tech: AppUser,
        item: ChecklistItem,
        recipe: CaptureRecipe,
    ) -> None:
        client_id = uuid.uuid4()
        sync(
            db,
            submitted_by=tech.id,
            envelope=EventEnvelope.model_validate(
                {"events": [capture_event(item, recipe, client_id=client_id)]}
            ),
        )
        result = store_blob(
            db,
            storage,
            BUCKET,
            client_id=client_id,
            data=PHOTO,
            content_hash=PHOTO_SHA,
            mime_type="image/jpeg",
        )
        assert result.evidence_confirmed is True
        assert evidence_for(db, client_id).status is EvidenceStatus.STORED
        assert storage.get(BUCKET, evidence_storage_key(client_id)) == PHOTO

    def test_bytes_before_the_event_are_confirmed_on_sync(
        self,
        db: Session,
        storage: InMemoryStorage,
        tech: AppUser,
        item: ChecklistItem,
        recipe: CaptureRecipe,
    ) -> None:
        """Neither order needs the other to have happened first."""
        client_id = uuid.uuid4()
        early = store_blob(
            db,
            storage,
            BUCKET,
            client_id=client_id,
            data=PHOTO,
            content_hash=PHOTO_SHA,
            mime_type="image/jpeg",
        )
        assert early.evidence_confirmed is False  # nothing to confirm yet

        sync(
            db,
            submitted_by=tech.id,
            envelope=EventEnvelope.model_validate(
                {"events": [capture_event(item, recipe, client_id=client_id)]}
            ),
        )
        assert evidence_for(db, client_id).status is EvidenceStatus.PENDING_UPLOAD

        assert confirm_uploads(db, storage, BUCKET) == 1
        assert evidence_for(db, client_id).status is EvidenceStatus.STORED

    def test_uploading_twice_is_not_an_error(self, db: Session, storage: InMemoryStorage) -> None:
        client_id = uuid.uuid4()
        kwargs = {
            "client_id": client_id,
            "data": PHOTO,
            "content_hash": PHOTO_SHA,
            "mime_type": "image/jpeg",
        }
        first = store_blob(db, storage, BUCKET, **kwargs)  # type: ignore[arg-type]
        second = store_blob(db, storage, BUCKET, **kwargs)  # type: ignore[arg-type]
        assert first.first_time is True
        assert second.first_time is False
        assert second.storage_key == first.storage_key

    def test_confirming_twice_promotes_nothing_the_second_time(
        self,
        db: Session,
        storage: InMemoryStorage,
        tech: AppUser,
        item: ChecklistItem,
        recipe: CaptureRecipe,
    ) -> None:
        client_id = uuid.uuid4()
        storage.put(BUCKET, evidence_storage_key(client_id), PHOTO, "image/jpeg")
        sync(
            db,
            submitted_by=tech.id,
            envelope=EventEnvelope.model_validate(
                {"events": [capture_event(item, recipe, client_id=client_id)]}
            ),
        )
        assert confirm_uploads(db, storage, BUCKET) == 1
        assert confirm_uploads(db, storage, BUCKET) == 0


class TestBytesThatAreNotWhatTheySay:
    def test_a_hash_mismatch_is_refused(self, db: Session, storage: InMemoryStorage) -> None:
        with pytest.raises(BlobRejectedError, match="do not match the hash"):
            store_blob(
                db,
                storage,
                BUCKET,
                client_id=uuid.uuid4(),
                data=b"different bytes entirely",
                content_hash=PHOTO_SHA,
                mime_type="image/jpeg",
            )

    def test_a_refused_upload_stores_nothing(self, db: Session, storage: InMemoryStorage) -> None:
        client_id = uuid.uuid4()
        with pytest.raises(BlobRejectedError):
            store_blob(
                db,
                storage,
                BUCKET,
                client_id=client_id,
                data=b"corrupted in transit",
                content_hash=PHOTO_SHA,
                mime_type="image/jpeg",
            )
        assert not storage.exists(BUCKET, evidence_storage_key(client_id))

    def test_an_empty_upload_is_refused(self, db: Session, storage: InMemoryStorage) -> None:
        with pytest.raises(BlobRejectedError, match="empty"):
            store_blob(
                db,
                storage,
                BUCKET,
                client_id=uuid.uuid4(),
                data=b"",
                content_hash=hashlib.sha256(b"").hexdigest(),
                mime_type="image/jpeg",
            )

    def test_a_corrupt_upload_leaves_the_row_pending(
        self,
        db: Session,
        storage: InMemoryStorage,
        tech: AppUser,
        item: ChecklistItem,
        recipe: CaptureRecipe,
    ) -> None:
        """The reviewer sees "not uploaded yet", never a corrupted photograph."""
        client_id = uuid.uuid4()
        sync(
            db,
            submitted_by=tech.id,
            envelope=EventEnvelope.model_validate(
                {"events": [capture_event(item, recipe, client_id=client_id)]}
            ),
        )
        with pytest.raises(BlobRejectedError):
            store_blob(
                db,
                storage,
                BUCKET,
                client_id=client_id,
                data=b"corrupted in transit",
                content_hash=PHOTO_SHA,
                mime_type="image/jpeg",
            )
        assert evidence_for(db, client_id).status is EvidenceStatus.PENDING_UPLOAD


class TestOverHttp:
    def test_upload_then_sync_leaves_the_row_stored(
        self,
        api: TestClient,
        db: Session,
        tech: AppUser,
        item: ChecklistItem,
        recipe: CaptureRecipe,
    ) -> None:
        client_id = uuid.uuid4()
        headers = {"X-Dev-User-Id": str(tech.id)}

        upload = api.post(
            f"/field/evidence/{client_id}/blob",
            headers=headers,
            data={"content_hash": PHOTO_SHA},
            files={"file": ("shot.jpg", PHOTO, "image/jpeg")},
        )
        assert upload.status_code == 200, upload.text
        assert upload.json()["storage_key"] == evidence_storage_key(client_id)

        synced = api.post(
            "/field/sync",
            headers=headers,
            json={"events": [capture_event(item, recipe, client_id=client_id)]},
        )
        assert synced.status_code == 200, synced.text
        assert evidence_for(db, client_id).status is EvidenceStatus.STORED

    def test_a_bad_hash_over_http_is_422(self, api: TestClient, tech: AppUser) -> None:
        response = api.post(
            f"/field/evidence/{uuid.uuid4()}/blob",
            headers={"X-Dev-User-Id": str(tech.id)},
            data={"content_hash": PHOTO_SHA},
            files={"file": ("shot.jpg", b"not the photo", "image/jpeg")},
        )
        assert response.status_code == 422
        assert "do not match the hash" in response.text

    def test_the_reviewer_can_open_the_photo_once_it_is_up(
        self,
        api: TestClient,
        db: Session,
        tech: AppUser,
        item: ChecklistItem,
        recipe: CaptureRecipe,
    ) -> None:
        """The whole point of the chain: bytes uploaded in the field open here."""
        client_id = uuid.uuid4()
        headers = {"X-Dev-User-Id": str(tech.id)}
        api.post(
            f"/field/evidence/{client_id}/blob",
            headers=headers,
            data={"content_hash": PHOTO_SHA},
            files={"file": ("shot.jpg", PHOTO, "image/jpeg")},
        )
        api.post(
            "/field/sync",
            headers=headers,
            json={"events": [capture_event(item, recipe, client_id=client_id)]},
        )
        evidence = evidence_for(db, client_id)

        reviewer = f.make_user(db, UserRole.REVIEWER)
        response = api.get(
            f"/review/evidence/{evidence.id}/image",
            headers={"X-Dev-User-Id": str(reviewer.id)},
        )
        assert response.status_code == 200
        assert response.content == PHOTO

    def test_a_photo_that_never_arrived_reads_as_not_uploaded(
        self,
        api: TestClient,
        db: Session,
        tech: AppUser,
        item: ChecklistItem,
        recipe: CaptureRecipe,
    ) -> None:
        client_id = uuid.uuid4()
        api.post(
            "/field/sync",
            headers={"X-Dev-User-Id": str(tech.id)},
            json={"events": [capture_event(item, recipe, client_id=client_id)]},
        )
        evidence = evidence_for(db, client_id)
        assert evidence.status is EvidenceStatus.PENDING_UPLOAD

        reviewer = f.make_user(db, UserRole.REVIEWER)
        response = api.get(
            f"/review/evidence/{evidence.id}/image",
            headers={"X-Dev-User-Id": str(reviewer.id)},
        )
        assert response.status_code == 404
        assert "not been uploaded" in response.text
