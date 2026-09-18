"""Evidence bytes, for whoever is allowed to see them.

One route rather than a reviewer copy and a field copy, because the thing that
differs between the two callers is the authorization rule, and duplicating a
route means duplicating the rule. It lives in `app.authz`.

Streamed through the API rather than linked straight at object storage: a signed
storage URL is a bearer token that outlives the session and answers to nobody, so
looking at a photograph needs the same identity as ruling on it.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Response, status

from app.authz import may_view_evidence
from app.deps import AppSettings, CurrentUser, DbSession, Storage
from app.models import Evidence
from app.storage import StorageError

router = APIRouter(prefix="/evidence", tags=["evidence"])

#: Said for both "no such id" and "not yours", so the response cannot be used to
#: work out which evidence exists.
_NOT_AVAILABLE = "No such photo, or it is not yours to look at."


@router.get("/{evidence_id}/image")
def read_evidence_image(
    evidence_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    storage: Storage,
) -> Response:
    """Stream one piece of evidence."""
    evidence = session.get(Evidence, evidence_id)
    if evidence is None or not may_view_evidence(user, evidence):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_AVAILABLE)

    try:
        body = storage.get(settings.evidence_bucket, evidence.storage_key)
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That photo has not been uploaded yet.",
        ) from exc

    return Response(content=body, media_type=evidence.mime_type)
