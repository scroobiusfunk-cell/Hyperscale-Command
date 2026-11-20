"""Render a VerificationResult as a JSON-able record and a Markdown report."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .compare import FieldStatus, OverallStatus, VerificationResult

_BADGE = {
    OverallStatus.PASS: "PASS",
    OverallStatus.DISCREPANCY: "**DISCREPANCY**",
    OverallStatus.NEEDS_REVIEW: "NEEDS REVIEW",
}


def to_record(result: VerificationResult, timestamp: Optional[str] = None) -> dict:
    """Structured record. The inspector block is intentionally blank: a human signs off."""
    return {
        "equip_id": result.equip_id,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "overall_status": result.overall.value,
        "overall_confidence": round(result.confidence, 3),
        "submittal_ref": result.submittal_ref,
        "capture_id": result.capture_id,
        "captured_at": result.captured_at,
        "evidence_photo": result.evidence_photo,
        "warnings": result.warnings,
        "fields": [
            {
                "name": f.name,
                "status": f.status.value,
                "critical": f.critical,
                "approved": f.approved,
                "observed_raw": f.observed_raw,
                "confidence": f.confidence,
                "reason": f.reason,
            }
            for f in result.fields
        ],
        "inspector": {"name": "", "signature": "", "signed_at": "", "disposition": "", "notes": ""},
    }


def to_markdown(result: VerificationResult, timestamp: Optional[str] = None) -> str:
    rec = to_record(result, timestamp)
    L = [
        f"# Nameplate Verification: {result.equip_id}",
        "",
        f"**Overall: {_BADGE[result.overall]}** (min field confidence {result.confidence:.2f})",
        "",
        "> Decision support only. This result is not an acceptance; the inspector must review and sign below.",
        "",
        f"- Submittal: {result.submittal_ref}",
        f"- Capture: {result.capture_id or 'n/a'} at {result.captured_at or 'n/a'}",
        f"- Report generated: {rec['timestamp']}",
        f"- Evidence photo: `{result.evidence_photo or 'none'}`",
        "",
    ]
    for w in result.warnings:
        L.append(f"- WARNING: {w}")
    if result.warnings:
        L.append("")

    bad = [f for f in result.fields if f.status == FieldStatus.MISMATCH]
    if bad:
        L += ["## DISCREPANCIES", ""]
        for f in bad:
            tag = " (SAFETY-CRITICAL)" if f.critical else ""
            L.append(f"- **{f.name}{tag}**: {f.reason}")
        L.append("")
    review = [f for f in result.fields if f.status in (FieldStatus.MISSING, FieldStatus.UNVERIFIABLE)]
    if review:
        L += ["## Needs human review", ""]
        L += [f"- {f.name}: {f.status.value} - {f.reason}" for f in review]
        L.append("")

    L += ["## Field detail", "",
          "| Field | Approved | Observed | Conf | Status | Reason |",
          "|---|---|---|---|---|---|"]
    for f in result.fields:
        status = f"**{f.status.value}**" if f.status == FieldStatus.MISMATCH else f.status.value
        conf = "-" if f.confidence is None else f"{f.confidence:.2f}"
        obs = "(none)" if f.observed_raw in (None, "") else f.observed_raw
        L.append(f"| {f.name}{'*' if f.critical else ''} | {f.approved} | {obs} | {conf} | {status} | {f.reason} |")
    L += ["", "\\* safety-critical field", "",
          "## Inspector sign-off", "",
          "- Inspector name: ______________________",
          "- Disposition (accept / reject / re-inspect): ______________",
          "- Signature / date: ______________________",
          "- Notes: ", ""]
    return "\n".join(L)
