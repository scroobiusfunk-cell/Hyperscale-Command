"""Evidence bytes, which travel separately from the event log.

The event log is small and the photographs are not. On a site with one bar of
signal the log syncs in a second and the photos trickle up over minutes, so the
two are deliberately decoupled:

- The device uploads each photograph's bytes here, one call per capture.
- The device syncs its event log, which *describes* the captures.

Either order works, and both are idempotent. An `Evidence` row created by replay
starts at `pending_upload` and becomes `stored` only once the bytes are actually
in object storage — never on the device's say-so. A row that claims a photograph
nobody can open is worse than no row at all: it reads as captured evidence on the
reviewer's screen and there is nothing behind it.

The storage key is derived here from the capture's client id and is never taken
from the device. A device that could name its own key could overwrite another
project's evidence.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models.enums import EvidenceStatus
from app.models.evidence import Evidence
from app.storage import ObjectStorage, StorageError

log = get_logger(__name__)


class BlobRejectedError(Exception):
    """The bytes did not match what the device said they were."""


def evidence_storage_key(client_id: uuid.UUID) -> str:
    """Where a capture's bytes live. Derived, never supplied by the device."""
    return f"evidence/{client_id}"


@dataclass(frozen=True)
class BlobStored:
    storage_key: str
    byte_size: int
    content_hash: str
    #: False when the same bytes were already there — a retry, not an error.
    first_time: bool
    #: True when an Evidence row was waiting on these bytes and is now `stored`.
    evidence_confirmed: bool


def store_blob(
    session: Session,
    storage: ObjectStorage,
    bucket: str,
    *,
    client_id: uuid.UUID,
    data: bytes,
    content_hash: str,
    mime_type: str,
) -> BlobStored:
    """Put one capture's bytes away and confirm any row waiting on them.

    The hash is verified here rather than trusted. A photograph that arrived
    corrupted must not be recorded as the evidence for a safety item.
    """
    if not data:
        raise BlobRejectedError("The upload was empty.")

    actual = hashlib.sha256(data).hexdigest()
    if actual != content_hash.lower():
        raise BlobRejectedError(
            f"The bytes do not match the hash the device sent "
            f"(expected {content_hash.lower()}, got {actual})."
        )

    key = evidence_storage_key(client_id)
    already_there = storage.exists(bucket, key)
    if not already_there:
        storage.put(bucket, key, data, mime_type)

    confirmed = _confirm_one(session, client_id=client_id, byte_size=len(data))
    log.info(
        "evidence.blob_stored",
        client_id=str(client_id),
        byte_size=len(data),
        first_time=not already_there,
        evidence_confirmed=confirmed,
    )
    return BlobStored(
        storage_key=key,
        byte_size=len(data),
        content_hash=actual,
        first_time=not already_there,
        evidence_confirmed=confirmed,
    )


def _confirm_one(session: Session, *, client_id: uuid.UUID, byte_size: int) -> bool:
    """Flip one waiting row to `stored`. Returns whether anything changed."""
    row = session.execute(
        select(Evidence).where(Evidence.client_id == client_id)
    ).scalar_one_or_none()
    if row is None or row.status is not EvidenceStatus.PENDING_UPLOAD:
        return False

    row.status = EvidenceStatus.STORED
    # The device reported a size before the upload. What arrived is the truth.
    row.byte_size = byte_size
    session.flush()
    return True


def confirm_uploads(
    session: Session,
    storage: ObjectStorage,
    bucket: str,
    *,
    client_ids: frozenset[uuid.UUID] | None = None,
) -> int:
    """Promote `pending_upload` rows whose bytes are present.

    Runs after every sync and is safe to run on its own as often as you like.
    It is how a capture whose bytes arrived before its event stops being stuck:
    neither order needs the other to have happened first.
    """
    query = select(Evidence).where(Evidence.status == EvidenceStatus.PENDING_UPLOAD)
    if client_ids is not None:
        if not client_ids:
            return 0
        query = query.where(Evidence.client_id.in_(client_ids))

    promoted = 0
    for row in session.execute(query).scalars():
        key = evidence_storage_key(row.client_id)
        if not storage.exists(bucket, key):
            continue
        try:
            size = len(storage.get(bucket, key))
        except StorageError:
            # It vanished between the check and the read. Leave it pending; a
            # later pass will pick it up if it comes back.
            continue
        row.status = EvidenceStatus.STORED
        row.byte_size = size
        promoted += 1

    if promoted:
        session.flush()
        log.info("evidence.uploads_confirmed", promoted=promoted)
    return promoted
