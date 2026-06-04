"""Assemble discharge draft from validated facts only — never raw PDF text.

Builds from extraction/validation state only — not raw PDF blobs.
"""

from __future__ import annotations

from typing import Any

from agent.schema import MISSING_DISPLAY, DischargeDraft, FieldStatus, MedicationEntry, SourcedValue


def _unwrap(sourced: Any) -> tuple[str | None, str | None, int | None, str | None]:
    if isinstance(sourced, dict):
        page = sourced.get("page") if sourced.get("page") is not None else sourced.get(
            "source_page"
        )
        return (
            sourced.get("value"),
            sourced.get("source_file"),
            int(page) if page is not None else None,
            sourced.get("evidence")
            or sourced.get("context")
            or sourced.get("source_note"),
        )
    if isinstance(sourced, str):
        return sourced, None, None, None
    return None, None, None, None


def _sv(
    sourced: Any,
    *,
    pending: bool = False,
    conflict: bool = False,
    extra_flags: list[str] | None = None,
) -> SourcedValue:
    value, source_file, page, evidence = _unwrap(sourced)
    flags = list(extra_flags or [])
    if value:
        status = FieldStatus.CONFLICT if conflict else FieldStatus.DOCUMENTED
        return SourcedValue(
            value=value,
            status=status,
            source_file=source_file,
            page=page,
            source_note=evidence,
            evidence=evidence,
            flags=flags,
        )
    if pending:
        return SourcedValue(
            value=None,
            status=FieldStatus.PENDING,
            flags=["Explicitly marked pending in source notes"],
            page=page,
            evidence=evidence,
        )
    flags.append(MISSING_DISPLAY)
    return SourcedValue(
        value=None,
        status=FieldStatus.MISSING,
        source_file=source_file,
        page=page,
        evidence=evidence,
        flags=flags,
    )


def build_draft(
    patient_id: str,
    validated_facts: dict[str, Any],
    med_entries: list[MedicationEntry],
    med_note: str,
    conflicts: list[dict[str, Any]],
    escalations: list[dict[str, Any]],
    pdf_failures: list[dict[str, Any]],
) -> DischargeDraft:
    """Build draft exclusively from validated_facts — no raw corpus access."""
    demo = validated_facts.get("demographics", {})
    demographics = {
        k: _sv(v) for k, v in demo.items()
    }
    if not demographics:
        demographics["name"] = _sv(None)

    allergies: list[SourcedValue] = []
    for m in validated_facts.get("allergy_mentions", []):
        st_conflict = any(c.get("field") == "allergies" for c in conflicts)
        text = m.get("text") if isinstance(m, dict) else str(m)
        allergies.append(
            _sv(
                {
                    "value": text,
                    "source_file": m.get("source_file") if isinstance(m, dict) else None,
                    "page": m.get("source_page") if isinstance(m, dict) else None,
                    "evidence": m.get("context") if isinstance(m, dict) else None,
                    "context": m.get("context") if isinstance(m, dict) else None,
                },
                conflict=st_conflict,
                extra_flags=["CONFLICTING_SOURCES"] if st_conflict else None,
            )
        )

    pending: list[SourcedValue] = []
    for p in validated_facts.get("pending_results", []):
        val, _, _, _ = _unwrap(p)
        is_pending = bool(val and ("pending" in val.lower() or "await" in val.lower()))
        pending.append(_sv(p, pending=is_pending))

    procedures = [_sv(p) for p in validated_facts.get("procedures", [])]
    secondary = [_sv(d) for d in validated_facts.get("secondary_diagnoses", [])]

    global_flags: list[str] = []
    if pdf_failures:
        global_flags.append(
            f"PDF_EXTRACTION_FAILED ({len(pdf_failures)} file(s)): sections may be incomplete"
        )
    global_flags.append("DRAFT — requires clinician sign-off")
    if conflicts:
        global_flags.append(f"{len(conflicts)} conflict(s) require resolution")

    draft = DischargeDraft(
        patient_id=patient_id,
        demographics=demographics,
        admission_date=_sv(validated_facts.get("admission_date")),
        discharge_date=_sv(validated_facts.get("discharge_date")),
        principal_diagnosis=_sv(validated_facts.get("principal_diagnosis")),
        secondary_diagnoses=secondary,
        hospital_course=_sv(validated_facts.get("hospital_course")),
        procedures=procedures,
        discharge_medications=med_entries,
        medication_reconciliation_notes=med_note,
        allergies=allergies,
        follow_up_instructions=_sv(validated_facts.get("follow_up")),
        pending_results=pending,
        discharge_condition=_sv(validated_facts.get("discharge_condition")),
        conflicts=conflicts,
        safety_escalations=escalations,
        global_flags=global_flags,
    )
    return draft
