"""Turning a grader result into a routing decision.

This is the flowchart in section 4 of the architecture doc, written as code:

    safety?                  -> reviewer
    item type not calibrated -> reviewer
    insufficient_evidence    -> recapture
    fail                     -> reviewer
    pass, above threshold    -> auto-clear
    pass, below threshold    -> reviewer

Two properties this module is built to guarantee, both of them tested
exhaustively rather than by example:

1. **A safety requirement never auto-clears.** Not at any confidence, not on any
   verdict, not with any calibration data, not through any ordering of the
   checks. The safety test runs before anything else looks at a threshold.
2. **A threshold is never a constant.** It comes from a `CalibrationSource`, and
   a source that has no answer means not calibrated, which means a reviewer. A
   number written here would be a number nobody measured.

Phase 1 uses `NoCalibration`, which has no answer for anything, so every item
routes to a reviewer. The whole path is still built and tested now, because the
alternative is writing it under pressure the week auto-clear is turned on.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.models.enums import Criticality, Verdict


class Routing(StrEnum):
    AUTO_CLEAR = "auto_clear"
    ROUTE_TO_REVIEWER = "route_to_reviewer"
    RECAPTURE = "recapture"


@dataclass(frozen=True)
class PolicyInput:
    """Everything the decision is allowed to depend on."""

    criticality: Criticality
    item_type: str
    verdict: Verdict | None = None
    """None when nothing has graded this item. Phase 1 is always None."""
    confidence: float | None = None


@dataclass(frozen=True)
class PolicyDecision:
    routing: Routing
    reason: str
    threshold_used: float | None = None
    """The calibrated threshold this decision was measured against, if any."""

    @property
    def clears(self) -> bool:
        return self.routing is Routing.AUTO_CLEAR


class CalibrationSource(Protocol):
    """Where auto-clear thresholds come from.

    `threshold_for` returns None when the item type is not calibrated — not a
    default, not a fallback number. Not calibrated means a person looks.
    """

    def threshold_for(self, item_type: str) -> float | None: ...


class NoCalibration(CalibrationSource):
    """Phase 1. Nothing is calibrated because nothing has been measured yet."""

    def threshold_for(self, item_type: str) -> float | None:
        return None


@dataclass(frozen=True)
class FixedCalibration(CalibrationSource):
    """A calibration source for tests and for the eval harness.

    Deliberately not importable as a production default: it exists so the
    auto-clear path can be exercised before the calibration job exists, and
    wiring it into a running system would be hardcoding the thresholds CLAUDE.md
    forbids.
    """

    thresholds: dict[str, float]

    def threshold_for(self, item_type: str) -> float | None:
        return self.thresholds.get(item_type)


def decide(item: PolicyInput, calibration: CalibrationSource | None = None) -> PolicyDecision:
    """Route one checklist item.

    The safety check is first and has no escape: no combination of verdict,
    confidence or calibration reaches the auto-clear branch for a safety item.
    """
    if item.criticality is Criticality.SAFETY:
        return PolicyDecision(
            routing=Routing.ROUTE_TO_REVIEWER,
            reason=(
                "This is a safety item. A qualified person rules on it every time, whatever "
                "the tool thinks."
            ),
        )

    source = calibration if calibration is not None else NoCalibration()

    if item.verdict is None:
        return PolicyDecision(
            routing=Routing.ROUTE_TO_REVIEWER,
            reason="Nothing has graded this item, so a person looks at it.",
        )

    threshold = source.threshold_for(item.item_type)
    if threshold is None:
        return PolicyDecision(
            routing=Routing.ROUTE_TO_REVIEWER,
            reason=(
                f"'{item.item_type}' has no calibrated threshold yet, so a person looks at it."
            ),
        )

    if item.verdict is Verdict.INDETERMINATE or item.verdict is Verdict.NOT_VISIBLE:
        return PolicyDecision(
            routing=Routing.RECAPTURE,
            reason="The evidence does not show enough to judge this. Take it again.",
            threshold_used=threshold,
        )

    if item.verdict is Verdict.FAIL:
        return PolicyDecision(
            routing=Routing.ROUTE_TO_REVIEWER,
            reason="The grader thinks this fails, so a person confirms it before it counts.",
            threshold_used=threshold,
        )

    if item.confidence is None:
        return PolicyDecision(
            routing=Routing.ROUTE_TO_REVIEWER,
            reason="The grader reported a pass without a confidence, so a person looks at it.",
            threshold_used=threshold,
        )

    if item.confidence > threshold:
        return PolicyDecision(
            routing=Routing.AUTO_CLEAR,
            reason=(
                f"Passed at {item.confidence:.2f}, above the calibrated threshold "
                f"{threshold:.2f} for '{item.item_type}'."
            ),
            threshold_used=threshold,
        )

    return PolicyDecision(
        routing=Routing.ROUTE_TO_REVIEWER,
        reason=(
            f"Passed at {item.confidence:.2f}, which is not above the calibrated threshold "
            f"{threshold:.2f} for '{item.item_type}'."
        ),
        threshold_used=threshold,
    )
