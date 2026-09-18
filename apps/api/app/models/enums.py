"""Enumerations shared by the ORM models and the API surface.

Values match `packages/schemas/` exactly. Where the architecture doc names a
closed set, the set is closed here too: `criticality` in particular drives the
safety routing rule, so an unrecognised value has to fail rather than fall
through to a default.
"""

from __future__ import annotations

from enum import StrEnum


class Criticality(StrEnum):
    SAFETY = "safety"
    CONTRACTUAL = "contractual"
    QUALITY = "quality"


class VerificationMethod(StrEnum):
    VISUAL = "visual"
    MEASURED = "measured"
    TESTED = "tested"
    DOCUMENTARY = "documentary"


class RequirementStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    RETIRED = "retired"


class DocumentType(StrEnum):
    SPEC_SECTION = "spec_section"
    APPROVED_SUBMITTAL = "approved_submittal"
    MANUFACTURER_IOM = "manufacturer_iom"
    STANDARD = "standard"
    RFI_RESPONSE = "rfi_response"


class AccessConstraint(StrEnum):
    """What a tech needs before they can check something.

    The architecture doc gates a walk on "which rooms are open, what is
    energized, whether a ladder is available", which only means anything if
    something records which items need what. This is that.
    """

    REQUIRES_DEENERGIZED = "requires_deenergized"
    REQUIRES_LADDER = "requires_ladder"
    REQUIRES_CONFINED_SPACE_ENTRY = "requires_confined_space_entry"


class TextLayerStatus(StrEnum):
    """Whether an ingested document carries machine-readable text."""

    PRESENT = "present"
    PARTIAL = "partial"
    MISSING = "missing"


class ReconciliationStatus(StrEnum):
    AUTO_MATCHED = "auto_matched"
    HUMAN_CONFIRMED = "human_confirmed"
    UNRESOLVED = "unresolved"


class AliasSource(StrEnum):
    """Listed in the order these sources are trusted for identity."""

    CXALLOY = "cxalloy"
    DRAWING_SCHEDULE = "drawing_schedule"
    SUBMITTAL = "submittal"
    NAMEPLATE = "nameplate"


class ChecklistItemState(StrEnum):
    OPEN = "open"
    EVIDENCE_CAPTURED = "evidence_captured"
    AUTO_CLEARED = "auto_cleared"
    ROUTED = "routed"
    REVIEWER_PASSED = "reviewer_passed"
    REVIEWER_FAILED = "reviewer_failed"
    BLOCKED = "blocked"


class BlockedReason(StrEnum):
    """The architecture doc requires deferrals to record a reason but gives the
    state enum no `deferred` value. `blocked` plus one of these is that deferral.
    """

    NO_ACCESS = "no_access"
    ENERGIZED = "energized"
    NOT_INSTALLED_YET = "not_installed_yet"
    EQUIPMENT_MISSING = "equipment_missing"
    TOOL_UNAVAILABLE = "tool_unavailable"
    OTHER = "other"


class CxAlloyDeliveryState(StrEnum):
    """CxAlloy's API is read only, so a ruling reaches the system of record only
    when a person imports it. See docs/adr/0001.
    """

    NOT_APPLICABLE = "not_applicable"
    PENDING_EXPORT = "pending_export"
    EXPORTED = "exported"
    DELIVERY_CONFIRMED = "delivery_confirmed"


class MediaType(StrEnum):
    PHOTO = "photo"
    VIDEO = "video"
    DOCUMENT = "document"
    MEASUREMENT = "measurement"


class PredictedVerdict(StrEnum):
    """The learner's own call, before the answer is shown.

    `UNSURE` is deliberate and is not a wasted answer. Forcing a binary guess
    teaches guessing; "I do not know" is the honest state a learner is often in,
    and it is the one a senior most wants to see. It is excluded from the
    agreement rate and counted on its own.
    """

    PASS = "pass"
    FAIL = "fail"
    UNSURE = "unsure"


class ReferenceKind(StrEnum):
    """Which side of the lesson an example illustrates."""

    GOOD = "good"
    WRONG = "wrong"


class EvidenceStatus(StrEnum):
    PENDING_UPLOAD = "pending_upload"
    STORED = "stored"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class GraderVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class RulingVerdict(StrEnum):
    """A recapture request is a ruling on the *evidence*, not on the
    installation, which is why it produces no LabeledExample.
    """

    PASS = "pass"
    FAIL = "fail"
    RECAPTURE_REQUESTED = "recapture_requested"


class UserRole(StrEnum):
    TECH = "tech"
    REVIEWER = "reviewer"
    CURATOR = "curator"
    ADMIN = "admin"
