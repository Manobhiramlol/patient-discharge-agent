"""Simulated clinician reviewer with consistent hidden editing policy."""

from __future__ import annotations

import re
from typing import Any

from agent.schema import DischargeDraft, FieldStatus, SourcedValue


class SimulatedReviewer:
    """
    Hidden policy (consistent across runs):
    - Expand MISSING principal diagnosis if secondary exists (copy first secondary — reviewer correction)
    - Remove speculative pending if marked MISSING without source
    - Standardize follow-up phrasing when documented
    - Add pharmacist note when med flags present
    """

    def edit(self, draft: DischargeDraft) -> dict[str, Any]:
        edited = draft.model_dump()
        edits: list[str] = []

        if draft.principal_diagnosis.status == FieldStatus.MISSING:
            if draft.secondary_diagnoses:
                first = draft.secondary_diagnoses[0]
                if first.value:
                    edited["principal_diagnosis"] = SourcedValue(
                        value=first.value,
                        status=FieldStatus.DOCUMENTED,
                        flags=["reviewer_inferred_from_secondary"],
                    ).model_dump()
                    edits.append("principal_diagnosis_filled_from_secondary")

        fu = draft.follow_up_instructions
        if fu.value and "pcP" not in fu.value and "PCP" not in fu.value:
            new_val = fu.value.rstrip(".") + ". Confirm PCP contact information."
            edited["follow_up_instructions"] = SourcedValue(
                value=new_val,
                status=FieldStatus.DOCUMENTED,
                flags=["reviewer_standardized_followup"],
            ).model_dump()
            edits.append("follow_up_standardized")

        med_flags = [m for m in draft.discharge_medications if m.flags]
        if med_flags and "pharmacist_review" not in str(edited.get("global_flags", [])):
            gf = list(edited.get("global_flags", []))
            gf.append("pharmacist_review_completed")
            edited["global_flags"] = gf
            edits.append("pharmacist_signoff_added")

        for pr in draft.pending_results:
            if pr.status == FieldStatus.MISSING and not pr.value:
                edits.append("removed_empty_pending_placeholder")

        edited_pending = [
            p.model_dump()
            for p in draft.pending_results
            if p.value or p.status != FieldStatus.MISSING
        ]
        edited["pending_results"] = edited_pending

        return {"edited_draft": edited, "edit_log": edits}


def section_match_rate(draft: dict, edited: dict) -> float:
    """Reward signal: fraction of top-level sections unchanged between draft and edit."""
    keys = [
        "principal_diagnosis",
        "hospital_course",
        "follow_up_instructions",
        "discharge_condition",
    ]
    matches = 0
    for k in keys:
        a = _norm_val(draft.get(k))
        b = _norm_val(edited.get(k))
        if a == b:
            matches += 1
    return matches / len(keys) if keys else 0.0


def _norm_val(v: Any) -> str:
    if isinstance(v, dict):
        return (v.get("value") or "").strip().lower()
    return str(v or "").strip().lower()
