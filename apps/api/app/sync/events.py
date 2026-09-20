"""What the device is allowed to send.

Strict schemas rather than trusting device JSON. An event that does not parse is
stored and rejected with the reason, never guessed at: a malformed capture event
whose fields were filled in with defaults would produce an evidence record that
looks real and is not.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.models.enums import BlockedReason, MediaType, Verdict, VerdictReason
from app.models.sync_event import SyncEventType


class GateResult(BaseModel):
    gate_id: str = Field(min_length=1)
    outcome: Literal["passed", "failed", "skipped"]
    measured_value: float | str | bool | None = None
    threshold: float | str | bool | None = None


class DeviceMetadata(BaseModel):
    model: str | None = None
    os_version: str | None = None
    app_version: str | None = None


class _Base(BaseModel):
    client_event_id: uuid.UUID
    client_walk_id: uuid.UUID
    sequence: int = Field(ge=0)
    occurred_at: datetime
    checklist_item_id: uuid.UUID | None = None


class ItemOpened(_Base):
    event_type: Literal[SyncEventType.ITEM_OPENED]
    checklist_item_id: uuid.UUID


class PredictionMade(_Base):
    """The learner's own call, made before anything was revealed to them.

    `disqualifier` names which one they believe they saw. It is free text here
    rather than an enum because the short list is the item's own
    `disqualifiers`, which are recipe data and change with a recipe version.

    `verdict_reason` is a different thing entirely and is only ever `unsure`
    from a device: it says which kind of `indeterminate` the verdict is. The two
    were both called `reason` until R-00.
    """

    event_type: Literal[SyncEventType.PREDICTION_MADE]
    checklist_item_id: uuid.UUID
    verdict: Verdict
    verdict_reason: VerdictReason | None = None
    disqualifier: str | None = Field(default=None, max_length=200)
    note: str | None = None


class CaptureTaken(_Base):
    event_type: Literal[SyncEventType.CAPTURE_TAKEN]
    checklist_item_id: uuid.UUID
    #: The evidence's own client id, separate from the event's. One capture can
    #: be reported by more than one event on a flaky connection.
    client_id: uuid.UUID
    capture_recipe_id: uuid.UUID
    capture_recipe_version: str
    step_index: int = Field(ge=0)
    media_type: MediaType = MediaType.PHOTO
    storage_key: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(gt=0)
    mime_type: str = Field(min_length=1)
    device_metadata: DeviceMetadata = Field(default_factory=DeviceMetadata)
    gate_results: list[GateResult] = Field(default_factory=list)
    retake_of_client_id: uuid.UUID | None = None


class GateFailed(_Base):
    event_type: Literal[SyncEventType.GATE_FAILED]
    checklist_item_id: uuid.UUID
    capture_recipe_id: uuid.UUID
    step_index: int = Field(ge=0)
    gate_results: list[GateResult] = Field(min_length=1)


class ItemCaptured(_Base):
    event_type: Literal[SyncEventType.ITEM_CAPTURED]
    checklist_item_id: uuid.UUID


class ItemDeferred(_Base):
    event_type: Literal[SyncEventType.ITEM_DEFERRED]
    checklist_item_id: uuid.UUID
    reason: BlockedReason
    note: str | None = None


class WalkCompleted(_Base):
    event_type: Literal[SyncEventType.WALK_COMPLETED]
    items_attempted: int = Field(ge=0)


IncomingEvent = Annotated[
    ItemOpened
    | PredictionMade
    | CaptureTaken
    | GateFailed
    | ItemCaptured
    | ItemDeferred
    | WalkCompleted,
    Field(discriminator="event_type"),
]


class EventEnvelope(BaseModel):
    """One sync upload: a batch of events from one device."""

    events: list[IncomingEvent] = Field(default_factory=list)


def payload_of(event: BaseModel) -> dict[str, Any]:
    """Everything about the event except the routing fields, stored as-is."""
    return event.model_dump(
        mode="json",
        exclude={
            "client_event_id",
            "client_walk_id",
            "sequence",
            "occurred_at",
            "checklist_item_id",
            "event_type",
        },
    )
