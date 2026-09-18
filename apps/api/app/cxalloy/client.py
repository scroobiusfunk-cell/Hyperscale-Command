"""The CxAlloy client.

Read only by construction. There is no `create_issue`, no `update_checklist`, no
`attach_photo` — not stubbed, not raising NotImplementedError, simply absent. A
stub that no-ops a write is worse than no method at all: a reader of the calling
code would reasonably assume the write happened.

The endpoint shapes are not confirmed, so the HTTP implementation is not written
yet. `FileEquipmentSource` exists because a CxAlloy equipment *export* is
available today, and the tag reconciler can be fed from one without waiting.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import ClassVar, Protocol

from app.logging import external_call, get_logger

log = get_logger(__name__)


class CxAlloyUnavailableError(RuntimeError):
    """The read API is not configured or could not be reached."""


@dataclass(frozen=True)
class CxAlloyEquipment:
    """One row of the CxAlloy equipment list, as the reconciler needs it."""

    cxalloy_id: str
    tag: str
    equipment_class: str | None = None
    system: str | None = None
    room: str | None = None


class EquipmentSource(Protocol):
    """Where the equipment list comes from. Reads only."""

    def fetch_equipment(self, project_ref: str) -> list[CxAlloyEquipment]: ...


class UnconfiguredCxAlloyApi(EquipmentSource):
    """The read API, before anyone has told us its endpoints.

    Fails loudly rather than returning an empty list: an empty equipment list
    looks exactly like a building with no equipment in it, and the reconciler
    would happily queue every tag in the project as unmatched.
    """

    def fetch_equipment(self, project_ref: str) -> list[CxAlloyEquipment]:
        raise CxAlloyUnavailableError(
            "The CxAlloy read API is not configured. Its endpoint shapes are not "
            "confirmed yet; use a CxAlloy equipment export in the meantime. "
            "See docs/adr/0001-cxalloy-read-only-results-export.md."
        )


class FileEquipmentSource(EquipmentSource):
    """A CxAlloy equipment export, read from CSV.

    Column names are matched case- and separator-insensitively, because the
    export's headers are whatever the person who ran it chose.
    """

    #: What each field might be called in an export.
    ALIASES: ClassVar[dict[str, tuple[str, ...]]] = {
        "cxalloy_id": ("cxalloyid", "id", "equipmentid", "recordid"),
        "tag": ("tag", "equipmenttag", "name", "equipmentname"),
        "equipment_class": ("equipmentclass", "class", "type", "equipmenttype"),
        "system": ("system", "systemname"),
        "room": ("room", "location", "space"),
    }

    def __init__(self, csv_bytes: bytes) -> None:
        self._csv_bytes = csv_bytes

    @staticmethod
    def _normalize(header: str) -> str:
        return "".join(c for c in header.lower() if c.isalnum())

    def _column_map(self, headers: list[str]) -> dict[str, str]:
        normalized = {self._normalize(h): h for h in headers}
        mapping: dict[str, str] = {}
        for field, aliases in self.ALIASES.items():
            for alias in aliases:
                if alias in normalized:
                    mapping[field] = normalized[alias]
                    break
        return mapping

    def fetch_equipment(self, project_ref: str) -> list[CxAlloyEquipment]:
        with external_call(
            "cxalloy", "fetch_equipment", version="file-export", project_ref=project_ref
        ) as record:
            reader = csv.DictReader(io.StringIO(self._csv_bytes.decode("utf-8-sig")))
            headers = reader.fieldnames or []
            mapping = self._column_map(list(headers))

            missing = {"cxalloy_id", "tag"} - set(mapping)
            if missing:
                raise CxAlloyUnavailableError(
                    f"The export has no column for {', '.join(sorted(missing))}. "
                    f"Columns found: {', '.join(headers) or 'none'}."
                )

            def value(row: dict[str, str], field: str) -> str | None:
                column = mapping.get(field)
                if column is None:
                    return None
                text = (row.get(column) or "").strip()
                return text or None

            equipment = [
                CxAlloyEquipment(
                    cxalloy_id=cx_id,
                    tag=tag,
                    equipment_class=value(row, "equipment_class"),
                    system=value(row, "system"),
                    room=value(row, "room"),
                )
                for row in reader
                if (cx_id := value(row, "cxalloy_id")) and (tag := value(row, "tag"))
            ]
            record["rows"] = len(equipment)
            return equipment
