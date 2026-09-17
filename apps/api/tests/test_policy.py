"""The policy layer.

CLAUDE.md names this one of the four places that need tests before merge, and
the reason is the first class below: the safety guarantee is the whole product.
It is tested by exhausting the input space rather than by example, because an
example test proves one path and the claim is about every path.
"""

from __future__ import annotations

import itertools

import pytest

from app.models.enums import Criticality, GraderVerdict
from app.policy import (
    FixedCalibration,
    NoCalibration,
    PolicyInput,
    Routing,
    decide,
)

ITEM_TYPE = "visual_presence.arc_flash_label"

ALL_VERDICTS: list[GraderVerdict | None] = [None, *list(GraderVerdict)]
ALL_CONFIDENCES: list[float | None] = [None, 0.0, 0.5, 0.94, 0.999, 1.0]
ALL_CALIBRATIONS = [
    NoCalibration(),
    FixedCalibration({}),
    FixedCalibration({ITEM_TYPE: 0.0}),
    FixedCalibration({ITEM_TYPE: 0.5}),
    FixedCalibration({ITEM_TYPE: 0.9}),
    FixedCalibration({ITEM_TYPE: 1.0}),
]


class TestSafetyNeverAutoClears:
    """The non-negotiable rule, over the whole input space."""

    def test_no_combination_of_inputs_clears_a_safety_item(self) -> None:
        cleared = [
            (verdict, confidence, calibration)
            for verdict, confidence, calibration in itertools.product(
                ALL_VERDICTS, ALL_CONFIDENCES, ALL_CALIBRATIONS
            )
            if decide(
                PolicyInput(
                    criticality=Criticality.SAFETY,
                    item_type=ITEM_TYPE,
                    verdict=verdict,
                    confidence=confidence,
                ),
                calibration,
            ).clears
        ]
        assert cleared == [], f"safety items cleared on {len(cleared)} input combinations"

    def test_a_safety_item_is_never_sent_for_recapture_either(self) -> None:
        """A tech recapturing forever is a safety item nobody ever rules on."""
        for verdict, confidence, calibration in itertools.product(
            ALL_VERDICTS, ALL_CONFIDENCES, ALL_CALIBRATIONS
        ):
            decision = decide(
                PolicyInput(
                    criticality=Criticality.SAFETY,
                    item_type=ITEM_TYPE,
                    verdict=verdict,
                    confidence=confidence,
                ),
                calibration,
            )
            assert decision.routing is Routing.ROUTE_TO_REVIEWER

    def test_the_reason_a_tech_sees_says_why(self) -> None:
        decision = decide(
            PolicyInput(criticality=Criticality.SAFETY, item_type=ITEM_TYPE),
            FixedCalibration({ITEM_TYPE: 0.5}),
        )
        assert "qualified person" in decision.reason
        assert decision.threshold_used is None, "no threshold was consulted"


class TestPhaseOneRoutesEverything:
    @pytest.mark.parametrize("criticality", list(Criticality))
    def test_with_no_grader_every_item_goes_to_a_reviewer(self, criticality: Criticality) -> None:
        decision = decide(PolicyInput(criticality=criticality, item_type=ITEM_TYPE))
        assert decision.routing is Routing.ROUTE_TO_REVIEWER

    def test_an_uncalibrated_item_type_routes_however_good_the_verdict(self) -> None:
        decision = decide(
            PolicyInput(
                criticality=Criticality.QUALITY,
                item_type=ITEM_TYPE,
                verdict=GraderVerdict.PASS,
                confidence=1.0,
            ),
            NoCalibration(),
        )
        assert decision.routing is Routing.ROUTE_TO_REVIEWER
        assert "no calibrated threshold" in decision.reason

    def test_an_unknown_item_type_is_not_calibrated(self) -> None:
        decision = decide(
            PolicyInput(
                criticality=Criticality.QUALITY,
                item_type="something.nobody.measured",
                verdict=GraderVerdict.PASS,
                confidence=1.0,
            ),
            FixedCalibration({ITEM_TYPE: 0.5}),
        )
        assert decision.routing is Routing.ROUTE_TO_REVIEWER


class TestTheCalibratedPath:
    """Unreachable in Phase 1, built and tested now rather than under pressure
    the week auto-clear is switched on."""

    calibration = FixedCalibration({ITEM_TYPE: 0.9})

    def _decide(self, **kwargs: object) -> object:
        return decide(
            PolicyInput(criticality=Criticality.QUALITY, item_type=ITEM_TYPE, **kwargs),  # type: ignore[arg-type]
            self.calibration,
        )

    def test_a_confident_pass_clears(self) -> None:
        decision = decide(
            PolicyInput(
                criticality=Criticality.QUALITY,
                item_type=ITEM_TYPE,
                verdict=GraderVerdict.PASS,
                confidence=0.95,
            ),
            self.calibration,
        )
        assert decision.routing is Routing.AUTO_CLEAR
        assert decision.threshold_used == 0.9

    def test_a_pass_exactly_at_the_threshold_does_not_clear(self) -> None:
        """Above the threshold, not at it. The boundary belongs to the reviewer."""
        decision = decide(
            PolicyInput(
                criticality=Criticality.QUALITY,
                item_type=ITEM_TYPE,
                verdict=GraderVerdict.PASS,
                confidence=0.9,
            ),
            self.calibration,
        )
        assert decision.routing is Routing.ROUTE_TO_REVIEWER

    def test_a_pass_with_no_confidence_does_not_clear(self) -> None:
        decision = decide(
            PolicyInput(
                criticality=Criticality.QUALITY,
                item_type=ITEM_TYPE,
                verdict=GraderVerdict.PASS,
                confidence=None,
            ),
            self.calibration,
        )
        assert decision.routing is Routing.ROUTE_TO_REVIEWER

    def test_a_fail_goes_to_a_person_however_confident(self) -> None:
        decision = decide(
            PolicyInput(
                criticality=Criticality.QUALITY,
                item_type=ITEM_TYPE,
                verdict=GraderVerdict.FAIL,
                confidence=1.0,
            ),
            self.calibration,
        )
        assert decision.routing is Routing.ROUTE_TO_REVIEWER

    def test_insufficient_evidence_asks_for_another_capture(self) -> None:
        decision = decide(
            PolicyInput(
                criticality=Criticality.QUALITY,
                item_type=ITEM_TYPE,
                verdict=GraderVerdict.INSUFFICIENT_EVIDENCE,
                confidence=0.2,
            ),
            self.calibration,
        )
        assert decision.routing is Routing.RECAPTURE
        assert "again" in decision.reason

    def test_contractual_items_use_the_same_path_as_quality(self) -> None:
        """Only `safety` is special. Contractual is calibrated like anything else."""
        decision = decide(
            PolicyInput(
                criticality=Criticality.CONTRACTUAL,
                item_type=ITEM_TYPE,
                verdict=GraderVerdict.PASS,
                confidence=0.95,
            ),
            self.calibration,
        )
        assert decision.routing is Routing.AUTO_CLEAR


class TestThresholdsAreNeverConstants:
    def test_the_default_source_has_no_answer_for_anything(self) -> None:
        source = NoCalibration()
        for item_type in ("", ITEM_TYPE, "visual_readable.nameplate", "anything at all"):
            assert source.threshold_for(item_type) is None

    def test_a_decision_reports_the_threshold_it_measured_against(self) -> None:
        """So an audit can check the decision against the calibration data of the day."""
        decision = decide(
            PolicyInput(
                criticality=Criticality.QUALITY,
                item_type=ITEM_TYPE,
                verdict=GraderVerdict.PASS,
                confidence=0.99,
            ),
            FixedCalibration({ITEM_TYPE: 0.93}),
        )
        assert decision.threshold_used == 0.93

    def test_raising_the_threshold_is_the_only_thing_that_changes_the_outcome(self) -> None:
        item = PolicyInput(
            criticality=Criticality.QUALITY,
            item_type=ITEM_TYPE,
            verdict=GraderVerdict.PASS,
            confidence=0.95,
        )
        assert decide(item, FixedCalibration({ITEM_TYPE: 0.9})).clears
        assert not decide(item, FixedCalibration({ITEM_TYPE: 0.96})).clears
