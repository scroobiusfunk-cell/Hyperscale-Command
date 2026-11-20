"""Nameplate extraction interface.

This module is the single seam where "pixels become fields". Everything
downstream (compare / report) only sees a NameplateReading.

FUTURE INTEGRATION POINTS (both are swappable Extractor adapters):
  * Smart-glasses / DAT camera layer: the capture app on the glasses produces
    a photo (and optionally a tag/QR id); it hands the image path/bytes to an
    Extractor. No change to compare/report is needed.
  * Real vision/OCR API: implemented in VisionExtractor below.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class NameplateReading:
    """What an extractor believes the nameplate says.

    fields:      field name -> raw extracted value (str/number) or None if not found
    confidence:  field name -> 0..1 extractor confidence (missing => treated as 0)
    evidence_photo: path/URI of the photo the values came from (audit trail)
    equip_id_tag: equipment tag read from the plate/QR/inspector selection, if any
    """
    fields: dict[str, Any] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)
    evidence_photo: str = ""
    equip_id_tag: Optional[str] = None
    capture_id: str = ""
    captured_at: str = ""


class Extractor(ABC):
    @abstractmethod
    def extract(self, source: str | Path) -> NameplateReading:
        """Turn a capture source (sidecar JSON or image) into a NameplateReading."""


class MockExtractor(Extractor):
    """Offline extractor: reads a sidecar JSON standing in for OCR output."""

    def extract(self, source: str | Path) -> NameplateReading:
        raw = json.loads(Path(source).read_text())
        fields_, conf = {}, {}
        for name, entry in raw.get("fields", {}).items():
            fields_[name] = entry.get("value")
            conf[name] = float(entry.get("confidence", 0.0))
        return NameplateReading(
            fields=fields_,
            confidence=conf,
            evidence_photo=raw.get("evidence_photo", ""),
            equip_id_tag=raw.get("equip_id_tag"),
            capture_id=raw.get("capture_id", ""),
            captured_at=raw.get("captured_at", ""),
        )


class VisionExtractor(Extractor):
    """STUB - real vision/OCR extractor. Not implemented in this MVP."""

    def extract(self, source: str | Path) -> NameplateReading:
        # TODO: call a vision/OCR model here.
        #   1. Read image bytes from `source` (photo from glasses/DAT camera or phone).
        #   2. Send to the vision API with a prompt/schema requesting the fields:
        #      manufacturer, model, voltage, amp_rating, aic_rating, poles
        #      -> each as {value, confidence}. Return value null if not legible;
        #      NEVER let the model guess or fill from "typical" values.
        #   3. Map the response into NameplateReading(fields=..., confidence=...,
        #      evidence_photo=str(source), equip_id_tag=<QR/tag if read>).
        #   Confidence must be calibrated/conservative; compare.py treats
        #   anything below its threshold as UNVERIFIABLE.
        raise NotImplementedError("VisionExtractor is a stub; use MockExtractor offline.")
