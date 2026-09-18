"""The built-in capture recipes.

Deterministic templates, not live generation: "the graders downstream depend on
evidence looking the same every time."

Phase 1 ships the two the build plan calls for, and their gates use no models.
The architecture doc specifies an object detector for presence and OCR for
readability; CLAUDE.md says Phase 1 ships without computer vision, and
OPEN_QUESTIONS Q1 settles that in favour of gates that measure the *capture*
rather than judging its *content*:

- sharpness is variance of Laplacian — arithmetic over pixels, no model and no
  opinion about what is in the frame
- frame fill is the share of the frame inside the on-screen guide
- shot count and the tech's own attestation are not measurements at all

Every gate result is stored on the evidence, so once a detector exists Phase 2
can ask what it would have caught that these did not.

Recipes are versioned and shared across projects, so they carry no project id.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CaptureRecipe
from app.models.enums import VerificationMethod


@dataclass(frozen=True)
class RecipeStep:
    instruction: str
    """Plain language, for a tech who has not read the specification."""
    framing_rule: str
    gate_check: str

    def as_json(self) -> dict[str, Any]:
        return {
            "instruction": self.instruction,
            "framing_rule": self.framing_rule,
            "gate_check": self.gate_check,
        }


@dataclass(frozen=True)
class RecipeDefinition:
    slug: str
    version: str
    verification_method: VerificationMethod
    steps: tuple[RecipeStep, ...]
    disqualifiers: tuple[str, ...]
    reference_media_slot: str | None = None
    gates: tuple[str, ...] = field(default=())
    """The on-device gates this recipe runs, named as they appear in evidence."""


VISUAL_PRESENCE = RecipeDefinition(
    slug="visual_presence",
    version="1.0.0",
    verification_method=VerificationMethod.VISUAL,
    steps=(
        RecipeStep(
            instruction="Take a wide shot showing the whole piece of equipment.",
            framing_rule="Stand back far enough that the whole enclosure is in the frame.",
            gate_check="sharpness_floor",
        ),
        RecipeStep(
            instruction="Take a close shot of the thing you are checking.",
            framing_rule="Fill most of the frame with it. Keep the camera square on.",
            gate_check="sharpness_floor",
        ),
    ),
    disqualifiers=(
        "glare across the subject",
        "something in the way",
        "blurred",
        "nothing in the shot to show which equipment this is",
    ),
    reference_media_slot="presence_reference",
    gates=("shot_count", "sharpness_floor", "min_resolution"),
)

VISUAL_READABLE = RecipeDefinition(
    slug="visual_readable",
    version="1.0.0",
    verification_method=VerificationMethod.VISUAL,
    steps=(
        RecipeStep(
            instruction="Photograph the label square on, close enough to read it.",
            framing_rule=(
                "Line the label up with the guide on screen. Stand square to it, not at an "
                "angle, and fill at least a third of the frame."
            ),
            gate_check="frame_fill",
        ),
        RecipeStep(
            instruction="Check you can read every line of the label in your own photo.",
            framing_rule="Zoom in on the photo you just took and read it back.",
            gate_check="tech_attestation",
        ),
    ),
    disqualifiers=(
        "glare across the text",
        "photographed at an angle",
        "too far away to read",
        "blurred",
    ),
    reference_media_slot="readable_reference",
    gates=("frame_fill", "sharpness_floor", "tech_attestation"),
)

BUILTIN_RECIPES: tuple[RecipeDefinition, ...] = (VISUAL_PRESENCE, VISUAL_READABLE)


def ensure_builtin_recipes(session: Session) -> list[CaptureRecipe]:
    """Create any built-in recipe that is not in the database yet.

    Idempotent, and it never edits a recipe already stored: evidence records
    which recipe version produced it, so changing one in place would silently
    rewrite what past captures were asked to do. A changed recipe is a new
    version.
    """
    stored: list[CaptureRecipe] = []
    for definition in BUILTIN_RECIPES:
        existing = session.execute(
            select(CaptureRecipe).where(
                CaptureRecipe.slug == definition.slug,
                CaptureRecipe.version == definition.version,
            )
        ).scalar_one_or_none()
        if existing is not None:
            stored.append(existing)
            continue

        recipe = CaptureRecipe(
            slug=definition.slug,
            version=definition.version,
            verification_method=definition.verification_method,
            steps=[step.as_json() for step in definition.steps],
            disqualifiers=list(definition.disqualifiers),
            reference_media_slot=definition.reference_media_slot,
        )
        session.add(recipe)
        stored.append(recipe)

    session.flush()
    return stored


RECIPES_BY_SLUG: dict[str, RecipeDefinition] = {r.slug: r for r in BUILTIN_RECIPES}


def stored_recipe_id(session: Session, definition: RecipeDefinition) -> uuid.UUID | None:
    """The database id of a recipe definition.

    The device has to name a capture recipe by id when it reports a capture, so
    the walk has to hand it one. Matching on slug *and* version matters: a
    capture must be attributable to the exact instructions the tech was given.

    A built-in with no row yet is seeded rather than reported missing, the same
    way `evidence_spec_for` does it. The alternative is a walk that silently
    drops every item because nobody remembered to seed reference data.
    """
    row = session.execute(
        select(CaptureRecipe).where(
            CaptureRecipe.slug == definition.slug,
            CaptureRecipe.version == definition.version,
        )
    ).scalar_one_or_none()
    if row is None:
        row = next(
            (
                r
                for r in ensure_builtin_recipes(session)
                if r.slug == definition.slug and r.version == definition.version
            ),
            None,
        )
    return None if row is None else row.id


def recipe_for_criteria(
    verification_method: VerificationMethod, pass_criteria: dict[str, Any] | None
) -> RecipeDefinition | None:
    """Which recipe captures the evidence for this kind of check.

    Phase 1 covers `visual` only, and chooses between presence and readable by
    what is being checked: a pattern to match means somebody has to read
    something. Anything else returns None — a requirement with no recipe is
    surfaced rather than given capture steps that do not fit, because a tech
    following the wrong steps produces evidence nobody can rule on.
    """
    if verification_method is not VerificationMethod.VISUAL:
        return None

    kind = (pass_criteria or {}).get("kind")
    if kind == "pattern":
        return RECIPES_BY_SLUG["visual_readable"]
    if kind == "presence":
        return RECIPES_BY_SLUG["visual_presence"]
    return None


def evidence_spec_for(session: Session, definition: RecipeDefinition) -> list[dict[str, str]]:
    """The `evidence_spec` entry pointing at a stored recipe."""
    recipe = session.execute(
        select(CaptureRecipe).where(
            CaptureRecipe.slug == definition.slug,
            CaptureRecipe.version == definition.version,
        )
    ).scalar_one_or_none()
    if recipe is None:
        (recipe,) = [
            r
            for r in ensure_builtin_recipes(session)
            if r.slug == definition.slug and r.version == definition.version
        ]
    return [{"capture_recipe_id": str(recipe.id), "version": recipe.version}]
