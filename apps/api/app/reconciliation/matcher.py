"""Scoring an incoming tag against known assets.

Pure functions: the matcher is given candidate assets and returns scores and a
decision. Nothing here touches the database, so every rule below is testable
without one.

Three signals, per the architecture doc: tag, location, equipment class.
Equipment class is a gate rather than a score — two records with different
known classes are not the same physical thing, however similar the tags look,
and that is the mismatch most likely to send a tech to the wrong panel.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from app.models.enums import AliasSource
from app.reconciliation.normalize import normalize_tag, strip_prefixes, tag_similarity


class MatchOutcome(StrEnum):
    AUTO_MATCHED = "auto_matched"
    QUEUED_AMBIGUOUS = "queued_ambiguous"
    QUEUED_LOW_CONFIDENCE = "queued_low_confidence"
    QUEUED_NO_MATCH = "queued_no_match"


@dataclass(frozen=True)
class MatchThresholds:
    """Named rather than inlined, so tuning them is a visible change.

    These are *reconciliation* thresholds, not the auto-clear thresholds that
    CLAUDE.md requires to come from calibration data. Nothing is cleared here;
    the worst outcome of a wrong value is more or less work in the queue.
    """

    auto_match: float = 0.93
    review_floor: float = 0.55
    ambiguity_margin: float = 0.05


DEFAULT_THRESHOLDS = MatchThresholds()

#: Sources trusted to establish identity on their own, in the doc's order. A
#: nameplate is what a tech read off a sticker in a dark room; it is evidence
#: that a tag exists, not authority to decide which asset it names.
IDENTITY_SOURCES = frozenset(
    {AliasSource.CXALLOY, AliasSource.DRAWING_SCHEDULE, AliasSource.SUBMITTAL}
)


@dataclass(frozen=True)
class TagObservation:
    """A tag as some source reported it."""

    raw_tag: str
    source: AliasSource
    equipment_class: str | None = None
    location_room: str | None = None


@dataclass(frozen=True)
class AssetCandidate:
    """The parts of an existing asset the matcher compares against."""

    asset_id: uuid.UUID
    tag: str
    equipment_class: str
    location_room: str | None = None
    known_aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScoredCandidate:
    asset_id: uuid.UUID
    score: float
    tag_score: float
    location_agrees: bool | None
    matched_against: str
    """The stored value that produced the best tag score: the tag or an alias."""


@dataclass(frozen=True)
class MatchDecision:
    outcome: MatchOutcome
    reason: str
    matched_asset_id: uuid.UUID | None = None
    scored: tuple[ScoredCandidate, ...] = field(default=())

    @property
    def is_auto_match(self) -> bool:
        return self.outcome is MatchOutcome.AUTO_MATCHED


def _location_agreement(observed: str | None, known: str | None) -> bool | None:
    """True, False, or None when either side does not know.

    Unknown is not disagreement. Penalising a missing room would push every
    submittal tag into the queue, which is how a reconciliation queue becomes
    noise nobody reads.
    """
    if observed is None or known is None:
        return None
    return normalize_tag(observed) == normalize_tag(known)


def score_candidate(
    observation: TagObservation,
    candidate: AssetCandidate,
    *,
    prefixes: frozenset[str] = frozenset(),
) -> ScoredCandidate | None:
    """Score one asset, or None when the equipment class rules it out."""
    if observation.equipment_class is not None and normalize_tag(
        observation.equipment_class
    ) != normalize_tag(candidate.equipment_class):
        return None

    observed_stripped = strip_prefixes(observation.raw_tag, prefixes)

    best_score = 0.0
    best_against = candidate.tag
    for known in (candidate.tag, *candidate.known_aliases):
        known_stripped = strip_prefixes(known, prefixes)
        for left in {observation.raw_tag, observed_stripped}:
            for right in {known, known_stripped}:
                score = tag_similarity(left, right)
                if score > best_score:
                    best_score, best_against = score, known

    location_agrees = _location_agreement(observation.location_room, candidate.location_room)

    # Location confirms or contradicts; it never carries a match on its own.
    if location_agrees is True:
        score = min(1.0, best_score + (1.0 - best_score) * 0.25)
    elif location_agrees is False:
        score = best_score * 0.6
    else:
        score = best_score

    return ScoredCandidate(
        asset_id=candidate.asset_id,
        score=round(score, 6),
        tag_score=round(best_score, 6),
        location_agrees=location_agrees,
        matched_against=best_against,
    )


def decide(
    observation: TagObservation,
    candidates: list[AssetCandidate],
    *,
    thresholds: MatchThresholds = DEFAULT_THRESHOLDS,
    prefixes: frozenset[str] = frozenset(),
) -> MatchDecision:
    """Resolve an observed tag to an asset, or send it to a person.

    Auto-matching requires all of: a score at or above the threshold, a clear
    margin over the runner-up, and a source trusted for identity. Anything else
    is queued with its candidates attached so the person deciding can see what
    the reconciler saw.
    """
    scored = sorted(
        (
            result
            for candidate in candidates
            if (result := score_candidate(observation, candidate, prefixes=prefixes)) is not None
        ),
        key=lambda s: s.score,
        reverse=True,
    )

    if not scored or scored[0].score < thresholds.review_floor:
        return MatchDecision(
            outcome=MatchOutcome.QUEUED_NO_MATCH,
            reason=(
                "No asset of a matching equipment class came close to this tag."
                if scored
                else "No asset of a matching equipment class was found."
            ),
            scored=tuple(scored),
        )

    best = scored[0]
    runner_up = scored[1] if len(scored) > 1 else None

    # Checked before the score thresholds, and against the unpenalised tag
    # score, because the location penalty would otherwise drop this into
    # "low confidence" and the person triaging the queue would lose the one
    # detail that explains it.
    if best.tag_score >= thresholds.auto_match and best.location_agrees is False:
        return MatchDecision(
            outcome=MatchOutcome.QUEUED_AMBIGUOUS,
            reason=(
                "The tag matches but the location does not. Either the tag is reused in "
                "another room or one of the records is wrong."
            ),
            scored=tuple(scored),
        )

    if runner_up is not None and (best.score - runner_up.score) < thresholds.ambiguity_margin:
        return MatchDecision(
            outcome=MatchOutcome.QUEUED_AMBIGUOUS,
            reason=(
                f"Two assets scored within {thresholds.ambiguity_margin} of each other "
                f"({best.score} and {runner_up.score}); a person has to pick."
            ),
            scored=tuple(scored),
        )

    if best.score < thresholds.auto_match:
        return MatchDecision(
            outcome=MatchOutcome.QUEUED_LOW_CONFIDENCE,
            reason=(
                f"Best score {best.score} is below the auto-match threshold "
                f"{thresholds.auto_match}."
            ),
            scored=tuple(scored),
        )

    if observation.source not in IDENTITY_SOURCES:
        return MatchDecision(
            outcome=MatchOutcome.QUEUED_LOW_CONFIDENCE,
            reason=(
                f"{observation.source.value} is not trusted to establish identity on its own, "
                "so this match needs confirming."
            ),
            scored=tuple(scored),
        )

    return MatchDecision(
        outcome=MatchOutcome.AUTO_MATCHED,
        reason=f"Matched on {best.matched_against} with score {best.score}.",
        matched_asset_id=best.asset_id,
        scored=tuple(scored),
    )
