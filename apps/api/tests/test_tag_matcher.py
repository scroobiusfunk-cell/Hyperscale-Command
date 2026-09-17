"""Match decisions. No database: every rule here is a pure function.

The question each test asks is the same one the reconciler asks: is this
certain enough to decide without a person?
"""

from __future__ import annotations

import uuid

from app.models.enums import AliasSource
from app.reconciliation.matcher import (
    AssetCandidate,
    MatchOutcome,
    MatchThresholds,
    TagObservation,
    decide,
    score_candidate,
)

SWBD_101 = uuid.UUID("11111111-1111-4111-8111-111111111111")
SWBD_102 = uuid.UUID("22222222-2222-4222-8222-222222222222")


def switchboard(
    asset_id: uuid.UUID = SWBD_101,
    tag: str = "SWBD-101",
    room: str | None = "Electrical Room 1-04",
    aliases: tuple[str, ...] = (),
) -> AssetCandidate:
    return AssetCandidate(
        asset_id=asset_id,
        tag=tag,
        equipment_class="switchboard",
        location_room=room,
        known_aliases=aliases,
    )


def observed(
    tag: str = "SWBD 101",
    source: AliasSource = AliasSource.CXALLOY,
    equipment_class: str | None = "switchboard",
    room: str | None = None,
) -> TagObservation:
    return TagObservation(
        raw_tag=tag, source=source, equipment_class=equipment_class, location_room=room
    )


class TestEquipmentClassIsAGate:
    def test_a_different_class_is_not_a_candidate_at_all(self) -> None:
        """The mismatch most likely to send a tech to the wrong panel."""
        air_handler = AssetCandidate(
            asset_id=SWBD_101, tag="SWBD-101", equipment_class="air_handler"
        )
        assert score_candidate(observed(), air_handler) is None

    def test_a_perfect_tag_with_the_wrong_class_still_does_not_match(self) -> None:
        air_handler = AssetCandidate(
            asset_id=SWBD_101, tag="SWBD-101", equipment_class="air_handler"
        )
        decision = decide(observed("SWBD-101"), [air_handler])
        assert decision.outcome is MatchOutcome.QUEUED_NO_MATCH
        assert decision.matched_asset_id is None

    def test_an_unstated_class_does_not_rule_a_candidate_out(self) -> None:
        decision = decide(observed("SWBD-101", equipment_class=None), [switchboard()])
        assert decision.is_auto_match


class TestConfidentMatches:
    def test_punctuation_variant_from_a_trusted_source_auto_matches(self) -> None:
        decision = decide(observed("SWBD 101"), [switchboard()])
        assert decision.outcome is MatchOutcome.AUTO_MATCHED
        assert decision.matched_asset_id == SWBD_101

    def test_a_known_alias_can_carry_the_match(self) -> None:
        decision = decide(observed("SB101"), [switchboard(tag="SWBD-101", aliases=("SB101",))])
        assert decision.is_auto_match

    def test_a_project_prefix_is_stripped_before_comparing(self) -> None:
        decision = decide(observed("DC07-SWBD-101"), [switchboard()], prefixes=frozenset({"DC07"}))
        assert decision.is_auto_match

    def test_an_unknown_location_does_not_block_a_match(self) -> None:
        """Submittal tags rarely carry a room; penalising that fills the queue with noise."""
        decision = decide(observed("SWBD-101", room=None), [switchboard(room="Room 1-04")])
        assert decision.is_auto_match

    def test_a_matching_location_is_recorded_as_agreement(self) -> None:
        decision = decide(
            observed("SWBD-101", room="Electrical Room 1-04"),
            [switchboard(room="Electrical Room 1-04")],
        )
        assert decision.is_auto_match
        assert decision.scored[0].location_agrees is True


class TestThingsAPersonDecides:
    def test_two_equally_good_candidates_are_never_guessed_between(self) -> None:
        decision = decide(
            observed("SWBD-10"),
            [switchboard(SWBD_101, "SWBD-101"), switchboard(SWBD_102, "SWBD-102")],
        )
        assert decision.outcome is MatchOutcome.QUEUED_AMBIGUOUS
        assert decision.matched_asset_id is None
        assert len(decision.scored) == 2

    def test_a_tag_that_matches_in_the_wrong_room_is_queued(self) -> None:
        """Either the tag is reused elsewhere or a record is wrong. Both need a person."""
        decision = decide(
            observed("SWBD-101", room="Electrical Room 2-01"),
            [switchboard(room="Electrical Room 1-04")],
        )
        assert decision.outcome is MatchOutcome.QUEUED_AMBIGUOUS
        assert "location" in decision.reason

    def test_a_nameplate_reading_never_auto_matches_on_its_own(self) -> None:
        """A nameplate is evidence a tag exists, not authority over which asset it names."""
        decision = decide(observed("SWBD-101", source=AliasSource.NAMEPLATE), [switchboard()])
        assert decision.outcome is MatchOutcome.QUEUED_LOW_CONFIDENCE
        assert decision.scored[0].score == 1.0, "it still scores well; it is just not trusted"

    def test_a_near_miss_is_queued_rather_than_assumed(self) -> None:
        decision = decide(observed("SWBD-1O1"), [switchboard()])
        assert decision.outcome in {
            MatchOutcome.QUEUED_LOW_CONFIDENCE,
            MatchOutcome.QUEUED_NO_MATCH,
        }
        assert decision.matched_asset_id is None

    def test_nothing_similar_is_reported_as_no_match(self) -> None:
        decision = decide(observed("AHU-7"), [switchboard()])
        assert decision.outcome is MatchOutcome.QUEUED_NO_MATCH

    def test_an_empty_project_queues_rather_than_failing(self) -> None:
        decision = decide(observed("SWBD-101"), [])
        assert decision.outcome is MatchOutcome.QUEUED_NO_MATCH
        assert decision.scored == ()


class TestThresholdsAreExplicit:
    def test_raising_the_threshold_turns_a_match_into_a_queue_entry(self) -> None:
        strict = MatchThresholds(auto_match=1.01)
        decision = decide(observed("SWBD 101"), [switchboard()], thresholds=strict)
        assert decision.outcome is MatchOutcome.QUEUED_LOW_CONFIDENCE

    def test_widening_the_ambiguity_margin_catches_closer_pairs(self) -> None:
        """SWBD-101 against SWBD-101 and SWBD-1011 scores 1.0 against 0.93.

        A 0.07 gap clears the default 0.05 margin, so it matches. A project
        whose tags differ by a trailing digit can widen the margin and have the
        same pair sent to a person instead.
        """
        candidates = [switchboard(SWBD_101, "SWBD-101"), switchboard(SWBD_102, "SWBD-1011")]

        assert decide(observed("SWBD-101"), candidates).is_auto_match

        careful = decide(
            observed("SWBD-101"), candidates, thresholds=MatchThresholds(ambiguity_margin=0.1)
        )
        assert careful.outcome is MatchOutcome.QUEUED_AMBIGUOUS
