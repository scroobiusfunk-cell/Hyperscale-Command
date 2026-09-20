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


class ReferenceKind(StrEnum):
    """Which side of the lesson an example illustrates."""

    GOOD = "good"
    WRONG = "wrong"


class EvidenceStatus(StrEnum):
    PENDING_UPLOAD = "pending_upload"
    STORED = "stored"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class Verdict(StrEnum):
    """The one verdict vocabulary, shared with the Rule Registry.

    Every judgement in the system is one of these four, whoever made it: a
    grader, a reviewer ruling on evidence, or a learner committing to a call
    before the reveal. Three separate enums said almost the same thing in
    slightly different words, which meant a reviewer's "send it back" and a
    learner's "I do not know" could not be compared or counted together even
    though both are the same shape of answer. See TASKS.md R-00.

    `indeterminate` is a first-class answer rather than a failure to answer, and
    it always carries a `VerdictReason` saying which kind it is.

    `not_visible` is narrower and nothing in Phase 1 produces it yet: it is for
    the case where the thing could not be seen at all, so no judgement about the
    installation was possible. The synthetic generator and the observability
    gate produce it; it is in the enum now because the vocabulary is shared and
    a value that exists in one repo and not the other is the drift this change
    exists to end.
    """

    PASS = "pass"
    FAIL = "fail"
    INDETERMINATE = "indeterminate"
    NOT_VISIBLE = "not_visible"


class VerdictReason(StrEnum):
    """Which kind of `indeterminate` this is.

    Set exactly when the verdict is `indeterminate`, null otherwise, and the
    database enforces the pairing on every table that stores a verdict. These
    three carry the meanings that used to be separate verdicts.
    """

    #: A grader without enough to go on. Never a silent pass.
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    #: A reviewer sending the photograph back. A judgement on the evidence, not
    #: on the installation, which is why it produces no LabeledExample and why
    #: the item reopens rather than resolving.
    RECAPTURE_REQUESTED = "recapture_requested"
    #: A learner who honestly does not know. Excluded from the agreement rate
    #: and counted on its own; forcing a binary guess teaches guessing.
    UNSURE = "unsure"


class UserRole(StrEnum):
    TECH = "tech"
    REVIEWER = "reviewer"
    CURATOR = "curator"
    ADMIN = "admin"
