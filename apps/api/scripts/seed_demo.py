"""Seed a demonstration project: one job, five checks, and a week of history.

Why this exists as a script rather than a fixture. A demo on an empty database
shows a shape; a demo on a database full of test leftovers shows bugs that are
not bugs — the prediction guard correctly refuses a call on an item that was
already ruled, and in front of an audience that reads as broken. This builds a
job that looks like a job: assets in rooms, requirements traced to clauses,
learners who were right about the obvious misses and wrong about the subtle
ones, and a queue with something still waiting in it.

It goes through the same services the applications use — `review.rule`,
`reference.add_reference`, `blobs.store_blob` — so the seeded state is state the
system could actually have reached. Nothing here writes a row a user could not.

The imagery is diagrams rather than photographs: a diagram can put the one
detail that matters in the middle of an otherwise empty frame, which is what a
worked example is for. Regenerate them with `scripts/reference_art.py`.

    python scripts/seed_demo.py

Prints the ids the reviewer console and the field client need.
"""

from __future__ import annotations

import hashlib
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.capture.recipes import (
    RECIPES_BY_SLUG,
    ensure_builtin_recipes,
    evidence_spec_for,
)
from app.coaching import reference
from app.config import Settings
from app.models import (
    AppUser,
    Asset,
    CaptureRecipe,
    ChecklistItem,
    Evidence,
    Prediction,
    Project,
    Requirement,
    RuleSet,
    SourceDocument,
)
from app.models.enums import (
    ChecklistItemState,
    Criticality,
    DocumentType,
    EvidenceStatus,
    MediaType,
    ReconciliationStatus,
    ReferenceKind,
    RequirementStatus,
    UserRole,
    Verdict,
    VerdictReason,
    VerificationMethod,
)
from app.requirements_compiler.grouping import item_type_of
from app.review import service as review
from app.storage import S3Storage
from app.sync.blobs import evidence_storage_key, store_blob

ART = Path(__file__).resolve().parent / "reference_art"
NOW = datetime.now(UTC)


# --------------------------------------------------------------- the people


@dataclass(frozen=True)
class Person:
    key: str
    name: str
    email: str
    role: UserRole


PEOPLE = (
    Person("ray", "Ray Okafor", "ray.okafor@example.com", UserRole.REVIEWER),
    Person("helen", "Helen Barrow", "helen.barrow@example.com", UserRole.REVIEWER),
    Person("dana", "Dana Reid", "dana.reid@example.com", UserRole.CURATOR),
    Person("jordan", "Jordan Pike", "jordan.pike@example.com", UserRole.TECH),
    Person("sam", "Sam Ferreira", "sam.ferreira@example.com", UserRole.TECH),
)


# ----------------------------------------------------------- what is checked


@dataclass(frozen=True)
class Check:
    key: str
    statement: str
    why: str
    criticality: Criticality
    recipe: str
    doc: str
    clause: str
    page: int
    criteria: dict[str, object]
    good: tuple[tuple[str, str], ...]
    wrong: tuple[tuple[str, str], ...]


CHECKS = (
    Check(
        key="filler_plates",
        statement="Every spare breaker position is closed off with a filler plate, seated flush.",
        why=(
            "An open position leaves a live part where a hand can reach it, and it is the "
            "easiest thing in the room to walk past."
        ),
        criticality=Criticality.QUALITY,
        recipe="visual_presence",
        doc="switchboards",
        clause="26 24 13 - 2.4.C",
        page=11,
        criteria={
            "kind": "presence",
            "expected": "present",
            "subject": "a filler plate in every spare position",
        },
        good=(
            (
                "filler_good",
                "All four spare ways closed off. The plates sit level with the breakers "
                "either side — that is what seated flush looks like.",
            ),
        ),
        wrong=(
            (
                "filler_missing",
                "Open positions with busbar visible behind. Obvious once you look, and "
                "the reason you open the dead front rather than judging from the door.",
            ),
            (
                "filler_proud",
                "The near miss: a plate is fitted but standing proud, so the gap is still "
                "there. Run a finger along the row — you will feel it before you see it.",
            ),
        ),
    ),
    Check(
        key="arc_flash_label",
        statement=(
            "An arc flash warning label is fitted to the door and readable from standing position."
        ),
        why=(
            "The label tells the next person what to wear before they open it. A label "
            "nobody can read from where they are standing is the same as no label."
        ),
        criticality=Criticality.SAFETY,
        recipe="visual_readable",
        doc="common",
        clause="26 05 00 - 1.8.B",
        page=4,
        criteria={
            "kind": "pattern",
            "pattern": "(?i)arc\s*flash",
            "description": (
                "The door carries an arc flash warning label and its text can be read from "
                "standing position."
            ),
        },
        good=(
            (
                "arcflash_good",
                "Fitted at eye height, square, and the incident energy and PPE category "
                "both readable without leaning in.",
            ),
        ),
        wrong=(
            ("arcflash_missing", "No label fitted. Nothing to argue about on this one."),
            (
                "arcflash_low",
                "Fitted, faded, and down by the plinth. You can read it crouching, which "
                "is not the test. The test is standing where you would be when you decide "
                "what to put on.",
            ),
        ),
    ),
    Check(
        key="circuit_directory",
        statement="A typed circuit directory is fitted inside the door and names every way.",
        why=(
            "At two in the morning somebody needs the right breaker first time. Spare ways "
            "left blank get filled in with a biro and then trusted."
        ),
        criticality=Criticality.QUALITY,
        recipe="visual_readable",
        doc="switchboards",
        clause="26 24 13 - 3.3.A",
        page=14,
        criteria={
            "kind": "presence",
            "expected": "present",
            "subject": "a typed circuit directory naming every way",
        },
        good=(
            (
                "directory_good",
                "Typed, in its holder, and spares marked SPARE rather than left empty. "
                "Every way accounted for.",
            ),
        ),
        wrong=(
            (
                "directory_hand",
                "Handwritten and half of it blank. This is the one people sign off because "
                "something is there.",
            ),
        ),
    ),
    Check(
        key="nameplate_tag",
        statement="The equipment nameplate matches the tag on the scheduled drawing.",
        why=(
            "A board labelled as its neighbour sends the next person to the wrong panel, "
            "and they will be carrying a lock."
        ),
        criticality=Criticality.QUALITY,
        recipe="visual_readable",
        doc="common",
        clause="26 05 00 - 2.9.A",
        page=6,
        criteria={
            "kind": "pattern",
            "pattern": "^[A-Z]{2,4}-[0-9]{1,3}[A-Z]?$",
            "description": "The nameplate reads exactly the tag the drawing schedules for it.",
        },
        good=(
            (
                "nameplate_good",
                "Nameplate and drawing agree, character for character. Photograph both in "
                "one frame so the reviewer does not have to take your word for it.",
            ),
        ),
        wrong=(
            (
                "nameplate_wrong",
                "One character out. Two boards of the same make sat side by side is exactly "
                "how this happens, and how it gets missed.",
            ),
        ),
    ),
    Check(
        key="ground_landed",
        statement="Each equipment grounding conductor is landed on its own lug and torque marked.",
        why=(
            "A shared or loose ground connection holds up fine until the day it is the only "
            "thing standing between somebody and the fault."
        ),
        criticality=Criticality.SAFETY,
        recipe="visual_presence",
        doc="grounding",
        clause="26 05 26 - 3.2.D",
        page=8,
        criteria={
            "kind": "presence",
            "expected": "present",
            "subject": "a torque mark on each grounding conductor lug",
        },
        good=(
            (
                "ground_good",
                "One conductor per lug, each with a torque stripe across the screw and the "
                "bar. The stripe is the evidence the wrench was on it.",
            ),
        ),
        wrong=(
            (
                "ground_double",
                "Two conductors under one lug. Tighten for one and the other is loose; "
                "tighten for both and neither is right.",
            ),
            (
                "ground_untorqued",
                "Landed correctly but no torque stripe on two of them. You cannot tell by "
                "eye whether they were pulled up, which is the whole point of the stripe.",
            ),
        ),
    ),
)

DOCS = {
    "common": ("26 05 00 Common Work Results for Electrical", DocumentType.SPEC_SECTION),
    "switchboards": ("26 24 13 Switchboards", DocumentType.SPEC_SECTION),
    "grounding": (
        "26 05 26 Grounding and Bonding for Electrical Systems",
        DocumentType.SPEC_SECTION,
    ),
}

ASSETS = (
    ("SWBD-2A", "switchboard", "Electrical Room 2-01", "normal power"),
    ("SWBD-2B", "switchboard", "Electrical Room 2-01", "normal power"),
    ("DP-2C", "panelboard", "Electrical Room 2-02", "normal power"),
    ("DP-2D", "panelboard", "Electrical Room 2-02", "normal power"),
    ("PP-2E", "panelboard", "Electrical Room 2-03", "normal power"),
)


# -------------------------------------------------------------- the history
#
# (asset, check, learner, their call, reviewer, ruling, the image they shot,
#  the reviewer's note). `None` for the ruling means it is still in the queue.

RULED = "ruled"
WAITING = "waiting"

HISTORY = (
    # Jordan, three weeks in. Solid on the obvious, walks past the subtle.
    (
        "SWBD-2A",
        "filler_plates",
        "jordan",
        "pass",
        "ray",
        "pass",
        "filler_good",
        "Correct. Worth noticing you photographed the whole row rather than the one gap — "
        "that is what lets me check the ones you did not flag.",
    ),
    (
        "SWBD-2A",
        "arc_flash_label",
        "jordan",
        "pass",
        "ray",
        "fail",
        "arcflash_low",
        "Fitted, but it is down at the plinth and faded. Readable from standing position is the "
        "requirement, not readable. Sent back to the contractor.",
    ),
    (
        "SWBD-2A",
        "circuit_directory",
        "jordan",
        "fail",
        "ray",
        "fail",
        "directory_hand",
        "Agreed, and good catch. Handwritten is a fail on its own; the blank spares make it two.",
    ),
    (
        "SWBD-2A",
        "nameplate_tag",
        "jordan",
        "pass",
        "ray",
        "pass",
        "nameplate_good",
        "Right, and you got both in one frame. Keep doing that.",
    ),
    (
        "SWBD-2A",
        "ground_landed",
        "jordan",
        "pass",
        "ray",
        "fail",
        "ground_untorqued",
        "Two of the three have no torque stripe. Landed is not the same as torqued — if there is "
        "no stripe you cannot tell, so it fails.",
    ),
    (
        "SWBD-2B",
        "filler_plates",
        "jordan",
        "fail",
        "helen",
        "fail",
        "filler_missing",
        "Correct. Two open ways with bus visible.",
    ),
    (
        "SWBD-2B",
        "arc_flash_label",
        "jordan",
        "fail",
        "helen",
        "fail",
        "arcflash_missing",
        "Correct, nothing fitted. You are catching the absent ones — it is the poor ones that "
        "are still getting past you.",
    ),
    (
        "SWBD-2B",
        "nameplate_tag",
        "jordan",
        "unsure",
        "helen",
        "fail",
        "nameplate_wrong",
        "Nameplate says 2B, the schedule says the 2A board is on the left as you come in. Unsure "
        "was the honest answer here and it is the right one to give — but the drawing settles it, "
        "so next time open E-201 before you call it.",
    ),
    (
        "SWBD-2B",
        "ground_landed",
        "jordan",
        "fail",
        "helen",
        "fail",
        "ground_double",
        "Correct. Two conductors under one lug.",
    ),
    # Sam, a superintendent learning what the inspection is actually looking for.
    (
        "DP-2C",
        "filler_plates",
        "sam",
        "pass",
        "ray",
        "fail",
        "filler_proud",
        "Third plate down is standing proud — there is still a gap behind it. Feel along the row "
        "with the back of your hand, you will find these quicker than you will see them.",
    ),
    (
        "DP-2C",
        "circuit_directory",
        "sam",
        "pass",
        "ray",
        "pass",
        "directory_good",
        "Correct. Typed, in the holder, spares marked.",
    ),
    (
        "DP-2C",
        "arc_flash_label",
        "sam",
        "pass",
        "ray",
        "pass",
        "arcflash_good",
        "Correct. Eye height, both figures legible.",
    ),
    (
        "DP-2C",
        "ground_landed",
        "sam",
        "pass",
        "ray",
        "pass",
        "ground_good",
        "Correct. One per lug and stripes on all three.",
    ),
    (
        "DP-2D",
        "filler_plates",
        "sam",
        "fail",
        "helen",
        "recapture",
        "filler_missing",
        "Cannot rule on this one — the shot is from too far back to see whether those are open "
        "ways or dark plates. Same framing as your last one on 2C please, dead front off and "
        "square to the board.",
    ),
    # Helen clears quickly and does not always write the pass up. Two silent
    # passes here are what makes the labelling-rate tile move: the flywheel
    # starves on items cleared without a note, and the console is where that
    # becomes visible before it becomes a habit.
    ("SWBD-2B", "circuit_directory", "sam", "pass", "helen", "pass", "directory_good", None),
    ("DP-2D", "circuit_directory", "jordan", "pass", "helen", "pass", "directory_good", None),
    (
        "PP-2E",
        "filler_plates",
        "sam",
        "pass",
        "helen",
        "pass",
        "filler_good",
        "Correct. Whole row in frame, which is what lets me check the ways you did not flag.",
    ),
    (
        "PP-2E",
        "arc_flash_label",
        "jordan",
        "pass",
        "helen",
        "pass",
        "arcflash_good",
        "Correct. Square, eye height, and both figures legible from where you were standing.",
    ),
    # Still in the queue, for the live part of the demo.
    ("DP-2D", "arc_flash_label", "sam", "fail", None, None, "arcflash_missing", None),
    ("DP-2D", "ground_landed", "jordan", "pass", None, None, "ground_untorqued", None),
    ("DP-2D", "nameplate_tag", "sam", "pass", None, None, "nameplate_good", None),
    ("DP-2C", "nameplate_tag", "jordan", "fail", None, None, "nameplate_wrong", None),
)

#: What the history above says, in the shared vocabulary. "unsure" and
#: "recapture" are both `indeterminate`; the reason is what tells them apart.
PREDICTED: dict[str, tuple[Verdict, VerdictReason | None]] = {
    "pass": (Verdict.PASS, None),
    "fail": (Verdict.FAIL, None),
    "unsure": (Verdict.INDETERMINATE, VerdictReason.UNSURE),
}
RULED_AS: dict[str, tuple[Verdict, VerdictReason | None]] = {
    "pass": (Verdict.PASS, None),
    "fail": (Verdict.FAIL, None),
    "recapture": (Verdict.INDETERMINATE, VerdictReason.RECAPTURE_REQUESTED),
}
DISQUALIFIER = {
    "filler_plates": "open position",
    "arc_flash_label": "not readable from standing position",
    "circuit_directory": "handwritten",
    "nameplate_tag": "tag does not match the schedule",
    "ground_landed": "no torque mark",
}


def art(name: str) -> bytes:
    path = ART / f"{name}.png"
    if not path.exists():
        raise SystemExit(
            f"Missing {path}. Run scripts/reference_art.py first (it needs a browser to "
            f"rasterise; see the docstring)."
        )
    return path.read_bytes()


def main() -> None:
    settings = Settings()
    engine = create_engine(str(settings.database_url))
    storage = S3Storage.from_settings(settings)

    with Session(engine) as db:
        project = Project(
            name="Northgate DC — Building A, Level 2 Fit-Out", cxalloy_project_id="CX-NGA-002"
        )
        db.add(project)
        db.flush()

        people = {}
        for person in PEOPLE:
            user = AppUser(
                oidc_subject=f"sso|demo|{person.key}|{uuid.uuid4().hex[:8]}",
                email=person.email,
                display_name=person.name,
                roles=[person.role],
            )
            db.add(user)
            people[person.key] = user
        db.flush()

        documents = {}
        for key, (title, doc_type) in DOCS.items():
            doc = SourceDocument(project_id=project.id, doc_type=doc_type, title=title)
            db.add(doc)
            documents[key] = doc
        db.flush()

        rule_set = RuleSet(project_id=project.id, version="1.0.0")
        db.add(rule_set)
        db.flush()

        ensure_builtin_recipes(db)
        recipes = {
            slug: evidence_spec_for(db, RECIPES_BY_SLUG[slug])
            for slug in ("visual_presence", "visual_readable")
        }

        requirements: dict[str, Requirement] = {}
        for check in CHECKS:
            requirement = Requirement(
                id=uuid.uuid4(),
                project_id=project.id,
                rule_set_id=rule_set.id,
                applies_to_equipment_class=["switchboard", "panelboard"],
                applies_to_system="normal_power",
                applies_to_location_type="electrical_room",
                statement=check.statement,
                verification_method=VerificationMethod.VISUAL,
                evidence_spec=recipes[check.recipe],
                pass_criteria=check.criteria,
                criticality=check.criticality,
                source_doc_id=documents[check.doc].id,
                source_clause=check.clause,
                source_page=check.page,
                precedence_rank=0,
                check_key=check.key,
                why_it_matters=check.why,
                status=RequirementStatus.APPROVED,
                approved_by=people["dana"].id,
                approved_at=NOW - timedelta(days=21),
                ruleset_version=rule_set.version,
            )
            db.add(requirement)
            requirements[check.key] = requirement
        db.flush()

        assets: dict[str, Asset] = {}
        for tag, equipment_class, room, system in ASSETS:
            asset = Asset(
                project_id=project.id,
                tag=tag,
                equipment_class=equipment_class,
                system=system,
                location_room=room,
                location_type="electrical_room",
                reconciliation_status=ReconciliationStatus.HUMAN_CONFIRMED,
            )
            db.add(asset)
            assets[tag] = asset
        db.flush()

        items: dict[tuple[str, str], ChecklistItem] = {}
        for tag, asset in assets.items():
            for check in CHECKS:
                item = ChecklistItem(
                    asset_id=asset.id,
                    requirement_id=requirements[check.key].id,
                    ruleset_version=rule_set.version,
                    state=ChecklistItemState.OPEN,
                )
                db.add(item)
                items[(tag, check.key)] = item
        db.flush()

        # Worked examples, added by the senior who would have added them.
        for check in CHECKS:
            item_type = item_type_of(requirements[check.key])
            order = 0
            sides = ((ReferenceKind.GOOD, check.good), (ReferenceKind.WRONG, check.wrong))
            for kind, pairs in sides:
                for name, caption in pairs:
                    reference.add_reference(
                        db,
                        storage,
                        settings.reference_bucket,
                        project_id=project.id,
                        item_type=item_type,
                        kind=kind,
                        caption=caption,
                        data=art(name),
                        mime_type="image/png",
                        added_by=people["ray"].id,
                        display_order=order,
                    )
                    order += 1

        recipe_rows: dict[str, CaptureRecipe] = {}
        for slug in recipes:
            recipe_row = db.get(CaptureRecipe, uuid.UUID(recipes[slug][0]["capture_recipe_id"]))
            if recipe_row is None:  # pragma: no cover - the recipe was just ensured
                raise SystemExit(f"Capture recipe {slug} went missing between write and read.")
            recipe_rows[slug] = recipe_row

        waiting = 0
        for offset, row in enumerate(HISTORY):
            tag, check_key, who, call, reviewer_key, verdict, image, note = row
            check = next(c for c in CHECKS if c.key == check_key)
            item = items[(tag, check_key)]
            requirement = requirements[check_key]
            item_type = item_type_of(requirement)
            learner = people[who]
            when = NOW - timedelta(days=9 - offset // 3, hours=offset % 7)

            db.add(
                Prediction(
                    checklist_item_id=item.id,
                    predicted_by=learner.id,
                    verdict=PREDICTED[call][0],
                    verdict_reason=PREDICTED[call][1],
                    disqualifier=DISQUALIFIER[check_key] if call == "fail" else None,
                    item_type=item_type,
                    created_at=when,
                )
            )

            data = art(image)
            client_id = uuid.uuid4()
            evidence = Evidence(
                client_id=client_id,
                checklist_item_id=item.id,
                capture_recipe_id=recipe_rows[check.recipe].id,
                capture_recipe_version=recipe_rows[check.recipe].version,
                step_index=0,
                media_type=MediaType.PHOTO,
                storage_key=evidence_storage_key(client_id),
                content_hash=hashlib.sha256(data).hexdigest(),
                byte_size=len(data),
                mime_type="image/png",
                captured_at=when + timedelta(minutes=4),
                received_at=when + timedelta(minutes=6),
                captured_by=learner.id,
                device_metadata={
                    "model": "Pixel 8",
                    "os_version": "Android 15",
                    "app_version": "0.1.0",
                },
                gate_results=[{"gate": "sharpness_floor", "passed": True, "value": 412.6}],
                status=EvidenceStatus.PENDING_UPLOAD,
            )
            db.add(evidence)
            db.flush()
            store_blob(
                db,
                storage,
                settings.evidence_bucket,
                client_id=client_id,
                data=data,
                content_hash=evidence.content_hash,
                mime_type="image/png",
            )
            item.state = ChecklistItemState.EVIDENCE_CAPTURED
            db.flush()

            if verdict is None or reviewer_key is None:
                waiting += 1
                continue

            review.rule(
                db,
                item.id,
                reviewer_id=people[reviewer_key].id,
                verdict=RULED_AS[verdict][0],
                verdict_reason=RULED_AS[verdict][1],
                note=note,
                item_type=item_type,
            )

        db.commit()

        open_items = [
            (tag, check.key)
            for tag in assets
            for check in CHECKS
            if items[(tag, check.key)].state is ChecklistItemState.OPEN
        ]

        print(f"PROJECT_ID={project.id}")
        print(f"PROJECT_NAME={project.name}")
        for key in ("ray", "helen", "jordan", "sam"):
            print(f"{key.upper()}={people[key].id}  # {people[key].display_name}")
        print(f"ASSET_PP_2E={assets['PP-2E'].id}")
        print(
            f"open_items={len(open_items)} awaiting_review={waiting} ruled={len(HISTORY) - waiting}"
        )


if __name__ == "__main__":
    main()
