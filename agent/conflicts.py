"""Detect conflicting information across sources — never resolve arbitrarily."""

from __future__ import annotations

from typing import Any


def _field_value(raw: Any) -> str | None:
    if isinstance(raw, dict):
        val = raw.get("value")
        return str(val) if val is not None else None
    if isinstance(raw, str):
        return raw
    return None


def _line_text(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("value") or item.get("description") or item)
    return str(item)


def detect_conflicts(facts: dict[str, Any]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []

    # Explicit conflicts embedded in synthetic notes
    for line in facts.get("documented_conflicts", []):
        conflicts.append(
            {
                "field": "documented",
                "description": _line_text(line),
                "sources": facts.get("sources", []),
                "resolution": "CLINICIAN_REVIEW_REQUIRED",
            }
        )

    # Allergy contradictions
    mentions = facts.get("allergy_mentions", [])
    if len(mentions) >= 2:
        texts = {m["text"].lower().strip() for m in mentions}
        sources = sorted({m.get("source_file", "") for m in mentions if m.get("source_file")})
        if len(texts) > 1:
            conflicts.append(
                {
                    "field": "allergies",
                    "description": (
                        "Conflicting allergy documentation across notes: "
                        + " | vs | ".join(sorted(texts))
                    ),
                    "values": list(texts),
                    "sources": sources,
                    "resolution": "CLINICIAN_REVIEW_REQUIRED",
                }
            )

    # NKDA vs specific allergy
    nkda = any("nkda" in m["text"].lower() or "no known" in m["text"].lower() for m in mentions)
    specific = any(
        m["text"].lower() not in ("nkda", "no known drug allergies", "none")
        and "no known" not in m["text"].lower()
        for m in mentions
    )
    if nkda and specific and len(mentions) >= 1:
        if not any(c.get("field") == "allergies" for c in conflicts):
            conflicts.append(
                {
                    "field": "allergies",
                    "description": "NKDA documented in one note but specific allergies in another",
                    "resolution": "CLINICIAN_REVIEW_REQUIRED",
                }
            )

    # Admission vs discharge date ordering (if both present)
    adm = _field_value(facts.get("admission_date"))
    dis = _field_value(facts.get("discharge_date"))
    if adm and dis and adm > dis:
        conflicts.append(
            {
                "field": "dates",
                "description": f"Admission date ({adm}) is after discharge date ({dis}) in sources",
                "resolution": "CLINICIAN_REVIEW_REQUIRED",
            }
        )

    return conflicts
