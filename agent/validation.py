"""Validate extracted facts and final draft before output."""

from __future__ import annotations

from typing import Any

from agent.schema import DischargeDraft, FieldStatus, SourcedValue
from agent.state import REQUIRED_DRAFT_FIELDS

_BANNER_FRAGMENT = "DRAFT FOR CLINICIAN REVIEW"
_REQUIRED_MARKDOWN_HEADINGS = (
    "## Patient demographics",
    "## Admission & discharge dates",
    "## Diagnoses",
    "## Hospital course",
    "## Discharge medications (vs admission)",
    "## Allergies",
    "## Follow-up instructions",
    "## Pending results",
    "## Discharge condition",
)


def validate_extracted_facts(extracted: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    """
    Produce validated_facts from extracted_facts.
    Drops values without source attribution; records missing_fields and issues.
    """
    validated: dict[str, Any] = {"sources": extracted.get("sources", [])}
    missing: list[str] = []
    issues: list[str] = []

    for field in REQUIRED_DRAFT_FIELDS:
        sourced = extracted.get(field)
        if _has_value(sourced):
            if not _has_source(sourced):
                issues.append(f"{field}: value present but no source file/page")
                missing.append(field)
            else:
                validated[field] = sourced
        else:
            missing.append(field)
            validated[field] = _missing_sourced(field)

    for field in ("demographics", "secondary_diagnoses", "procedures", "follow_up"):
        val = extracted.get(field)
        if val:
            validated[field] = val

    for field in ("admission_medications", "discharge_medications"):
        meds = extracted.get(field, [])
        validated[field] = meds
        if not meds:
            missing.append(field)

    allergy_mentions = extracted.get("allergy_mentions", [])
    validated["allergy_mentions"] = allergy_mentions
    if not allergy_mentions:
        missing.append("allergies")

    pending = extracted.get("pending_results", [])
    validated["pending_results"] = pending
    pending_values = [_unwrap(p) for p in pending if _unwrap(p)]
    validated["pending_result_values"] = pending_values

    validated["documented_conflicts"] = extracted.get("documented_conflicts", [])

    return validated, missing, issues


def _iter_sourced_values(draft: DischargeDraft) -> list[SourcedValue]:
    values: list[SourcedValue] = list(draft.demographics.values())
    values.extend(
        [
            draft.admission_date,
            draft.discharge_date,
            draft.principal_diagnosis,
            draft.hospital_course,
            draft.follow_up_instructions,
            draft.discharge_condition,
        ]
    )
    values.extend(draft.secondary_diagnoses)
    values.extend(draft.procedures)
    values.extend(draft.allergies)
    values.extend(draft.pending_results)
    return values


def validate_draft(draft: DischargeDraft) -> list[str]:
    """Pre-output checks: sections, banner, conflicts, and pending surfacing."""
    issues: list[str] = []

    if not draft.review_banner or _BANNER_FRAGMENT not in draft.review_banner:
        issues.append("Review banner missing or does not contain required DRAFT text")

    md = draft.to_markdown()
    if f"> **{draft.review_banner}**" not in md:
        issues.append("Review banner not rendered in draft markdown")

    for heading in _REQUIRED_MARKDOWN_HEADINGS:
        if heading not in md:
            issues.append(f"Required section missing from markdown: {heading}")

    sourced = _iter_sourced_values(draft)
    if any(sv.status == FieldStatus.CONFLICT for sv in sourced) and not draft.conflicts:
        issues.append(
            "One or more fields are marked CONFLICT but conflicts list is empty"
        )

    has_pending_status = any(sv.status == FieldStatus.PENDING for sv in sourced)
    pending_surfaced = bool(draft.pending_results) or any(
        "pending" in f.lower() for f in draft.global_flags
    )
    if has_pending_status and not pending_surfaced:
        issues.append(
            "PENDING field status present but pending results not surfaced in draft"
        )

    return issues


def validate_draft_strict(
    draft: DischargeDraft, missing_fields: list[str], validated_facts: dict[str, Any] | None = None
) -> tuple[bool, list[str]]:
    """Planner-time validation including missing_fields cross-checks and unsupported claim detection."""
    issues = list(validate_draft(draft))

    for field in REQUIRED_DRAFT_FIELDS:
        sv = getattr(draft, field, None)
        if sv is None:
            issues.append(f"Required section missing from draft: {field}")
            continue
        if field in missing_fields and sv.status not in (
            FieldStatus.MISSING,
            FieldStatus.PENDING,
            FieldStatus.CONFLICT,
        ):
            issues.append(f"{field}: marked documented but listed in missing_fields")

    for mf in missing_fields:
        if mf in ("admission_medications", "discharge_medications", "allergies"):
            continue
        sv = getattr(draft, mf, None)
        if sv and hasattr(sv, "status") and sv.status == FieldStatus.DOCUMENTED:
            if not sv.source_file:
                issues.append(f"Unsupported claim: {mf} documented without source_file")

    # Comprehensive unsupported claim validation
    if validated_facts:
        issues.extend(_validate_unsupported_claims(draft, validated_facts))

    ok = not any("Unsupported claim" in i for i in issues)
    return ok, issues


def _validate_unsupported_claims(draft: DischargeDraft, validated_facts: dict[str, Any]) -> list[str]:
    """Verify every claim in draft exists in validated_facts."""
    issues = []
    
    # Check principal diagnosis
    if draft.principal_diagnosis and draft.principal_diagnosis.status == FieldStatus.DOCUMENTED:
        validated_diag = validated_facts.get("principal_diagnosis", {})
        if not validated_diag.get("value"):
            issues.append("Unsupported claim: principal_diagnosis not in validated_facts")
    
    # Check admission/discharge dates
    for field in ("admission_date", "discharge_date"):
        sv = getattr(draft, field, None)
        if sv and sv.status == FieldStatus.DOCUMENTED:
            validated = validated_facts.get(field, {})
            if not validated.get("value"):
                issues.append(f"Unsupported claim: {field} not in validated_facts")
    
    # Check hospital course
    if draft.hospital_course and draft.hospital_course.status == FieldStatus.DOCUMENTED:
        validated = validated_facts.get("hospital_course", {})
        if not validated.get("value"):
            issues.append("Unsupported claim: hospital_course not in validated_facts")
    
    # Check discharge condition
    if draft.discharge_condition and draft.discharge_condition.status == FieldStatus.DOCUMENTED:
        validated = validated_facts.get("discharge_condition", {})
        if not validated.get("value"):
            issues.append("Unsupported claim: discharge_condition not in validated_facts")
    
    # Check follow-up
    if draft.follow_up_instructions and draft.follow_up_instructions.status == FieldStatus.DOCUMENTED:
        validated = validated_facts.get("follow_up", {})
        if not validated.get("value"):
            issues.append("Unsupported claim: follow_up not in validated_facts")
    
    return issues


def _has_value(sourced: Any) -> bool:
    if isinstance(sourced, dict):
        return bool(sourced.get("value"))
    return bool(sourced)


def _has_source(sourced: Any) -> bool:
    if isinstance(sourced, dict):
        return bool(sourced.get("source_file"))
    return False


def _unwrap(item: Any) -> str | None:
    if isinstance(item, dict):
        return item.get("value")
    return item if isinstance(item, str) else None


def _missing_sourced(field: str) -> dict[str, Any]:
    return {
        "value": None,
        "source_file": None,
        "source_page": None,
        "status": "missing",
        "missing_reason": f"MISSING — not documented in source notes ({field})",
    }
