"""Approved-equipment registry: typed records loaded from registry.json."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_REGISTRY = Path(__file__).resolve().parent.parent / "data" / "approved" / "registry.json"


@dataclass(frozen=True)
class ApprovedItem:
    equip_id: str
    type: str
    manufacturer: str
    model: str
    voltage: str
    amp_rating: Optional[float]   # amperes
    aic_rating: Optional[float]   # kA interrupting rating; None if not applicable
    poles: Optional[int]          # None if not applicable
    spec_section: str
    submittal_ref: str


class Registry:
    def __init__(self, items: list[ApprovedItem]):
        self._items = list(items)
        self._by_id = {i.equip_id: i for i in self._items}

    @classmethod
    def load(cls, path: Path | str = DEFAULT_REGISTRY) -> "Registry":
        data = json.loads(Path(path).read_text())
        return cls([ApprovedItem(**row) for row in data["items"]])

    def get(self, equip_id: str) -> Optional[ApprovedItem]:
        return self._by_id.get(equip_id)

    def by_type(self, type_: str) -> list[ApprovedItem]:
        return [i for i in self._items if i.type == type_]

    def all(self) -> list[ApprovedItem]:
        return list(self._items)
