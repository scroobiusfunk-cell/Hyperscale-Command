"""The shared schemas and the API's enums must say the same thing.

`packages/schemas` is described in CLAUDE.md as "the contract between all three
apps", and the convention is to generate from it rather than hand-write a
duplicate. Nothing enforced that. A copy in the field app had drifted to
`performance | documentation` against this side's `contractual | quality`, and
it had drifted silently, because a hand-written union is only wrong at the
moment somebody sends one of the values across.

So this is the fence on the Python side: every enum that also appears in a
schema is checked against it, by value. A new member added in one place and
forgotten in the other fails here rather than in the field.

Values, not names. The wire carries `not_installed_yet`; whether the Python
member is called `NOT_INSTALLED_YET` is this side's business.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.models.enums import (
    AliasSource,
    BlockedReason,
    ChecklistItemState,
    Criticality,
    CxAlloyDeliveryState,
    EvidenceStatus,
    GraderVerdict,
    MediaType,
    ReconciliationStatus,
    RequirementStatus,
    VerificationMethod,
)

SCHEMAS = Path(__file__).resolve().parents[3] / "packages" / "schemas" / "schemas"


def at(document: str, *path: str | int) -> list[str]:
    """The enum at a path in a schema file, so a move is a loud failure."""
    node: Any = json.loads((SCHEMAS / document).read_text())
    for step in path:
        node = node[step]
    enum = node["enum"]
    assert isinstance(enum, list), f"{document}{list(path)} is not an enum"
    return [str(value) for value in enum]


# (what it is, the schema's values, the Python enum)
PAIRS = [
    (
        "criticality",
        lambda: at("common/definitions.schema.json", "$defs", "criticality"),
        Criticality,
    ),
    (
        "verification_method",
        lambda: at("common/definitions.schema.json", "$defs", "verification_method"),
        VerificationMethod,
    ),
    (
        "requirement.status",
        lambda: at("requirement.schema.json", "properties", "status"),
        RequirementStatus,
    ),
    (
        "asset.reconciliation_status",
        lambda: at("asset.schema.json", "properties", "reconciliation_status"),
        ReconciliationStatus,
    ),
    (
        "asset.alias.source",
        lambda: at("asset.schema.json", "$defs", "alias", "properties", "source"),
        AliasSource,
    ),
    (
        "checklist_item.state",
        lambda: at("checklist-item.schema.json", "properties", "state"),
        ChecklistItemState,
    ),
    (
        "checklist_item.blocked_reason",
        lambda: at("checklist-item.schema.json", "properties", "blocked_reason", "oneOf", 0),
        BlockedReason,
    ),
    (
        "checklist_item.cxalloy_delivery_state",
        lambda: at("checklist-item.schema.json", "properties", "cxalloy_delivery_state"),
        CxAlloyDeliveryState,
    ),
    (
        "evidence.media_type",
        lambda: at("evidence.schema.json", "properties", "media_type"),
        MediaType,
    ),
    (
        "evidence.status",
        lambda: at("evidence.schema.json", "properties", "status"),
        EvidenceStatus,
    ),
    (
        "grader_result.verdict",
        lambda: at("grader-result.schema.json", "properties", "verdict"),
        GraderVerdict,
    ),
]


@pytest.mark.parametrize("name,read_schema,enum", PAIRS, ids=[p[0] for p in PAIRS])
def test_the_enum_matches_the_schema(name: str, read_schema: Any, enum: Any) -> None:
    assert sorted(read_schema()) == sorted(member.value for member in enum), (
        f"{name} has drifted between packages/schemas and app.models.enums. "
        f"Change both, in the same commit, or the wire stops meaning one thing."
    )


def test_the_schemas_are_where_this_test_thinks_they_are() -> None:
    """A moved package would otherwise make every pair above silently unrunnable."""
    assert SCHEMAS.is_dir(), f"No schemas at {SCHEMAS}"
