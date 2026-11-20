"""QA/QC inspection checklist: the spine that binds voice guidance, gate profile,
expected values and evidence requirements for each inspection step."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class VoiceScript:
    """What the (display-less) inspector hears for one item."""
    look: str                 # where to look
    frame: str                # how to frame the shot
    hint: str = ""            # optional extra tip
    safety: str = ""          # optional safety reminder, spoken first


@dataclass(frozen=True)
class ChecklistItem:
    id: str
    prompt: str                       # the inspection question
    equip_id: str                     # reference into the approved registry
    profile_key: str                  # inspection_profile: placard_large / nameplate_small / serial_tag
    voice: VoiceScript
    expected_fields: Optional[dict[str, Any]] = None   # overrides registry values per field
    evidence_required: bool = True


@dataclass
class Checklist:
    id: str
    name: str
    items: list[ChecklistItem] = field(default_factory=list)

    @classmethod
    def load_from_json(cls, path: Path | str) -> "Checklist":
        data = json.loads(Path(path).read_text())
        items = [
            ChecklistItem(
                id=row["id"],
                prompt=row["prompt"],
                equip_id=row["equip_id"],
                profile_key=row["profile_key"],
                voice=VoiceScript(**row["voice"]),
                expected_fields=row.get("expected_fields"),
                evidence_required=row.get("evidence_required", True),
            )
            for row in data["items"]
        ]
        return cls(id=data["id"], name=data["name"], items=items)
