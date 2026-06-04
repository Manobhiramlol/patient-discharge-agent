"""Structured agent state — single source of truth for the replanning loop."""

from __future__ import annotations

from typing import Any, TypedDict

from agent.schema import DischargeDraft, MedicationEntry


class AgentState(TypedDict, total=False):
    patient_id: str
    pdf_paths: list[str]
    corpus: dict[str, str]
    corpus_pages: dict[str, list[str]]
    pdf_failures: list[dict[str, Any]]
    extracted_facts: dict[str, Any]
    validated_facts: dict[str, Any]
    facts_extracted: bool
    facts_validated: bool
    missing_fields: list[str]
    med_entries: list[MedicationEntry]
    meds_reconciled: bool
    med_note: str
    conflicts: list[dict[str, Any]]
    conflicts_checked: bool
    pending_results: list[str]
    interactions: list[dict[str, Any]]
    drug_interaction_checked: bool
    escalation_flags: list[str]
    document_quality: dict[str, Any]
    escalations: list[dict[str, Any]]
    needs_escalation: bool
    escalation_done: bool
    escalation_message: str
    escalation_type: str
    escalation_severity: str
    open_flags: list[str]
    draft: DischargeDraft | None
    draft_built: bool
    draft_validated: bool
    validation_issues: list[str]
    iteration_count: int
    finished: bool


REQUIRED_DRAFT_FIELDS = (
    "principal_diagnosis",
    "admission_date",
    "discharge_date",
    "hospital_course",
    "discharge_condition",
)


def initial_state(patient_id: str, pdf_paths: list[str]) -> AgentState:
    return AgentState(
        patient_id=patient_id,
        pdf_paths=pdf_paths,
        corpus={},
        corpus_pages={},
        pdf_failures=[],
        extracted_facts={},
        validated_facts={},
        facts_extracted=False,
        facts_validated=False,
        missing_fields=[],
        med_entries=[],
        meds_reconciled=False,
        med_note="",
        conflicts=[],
        conflicts_checked=False,
        pending_results=[],
        interactions=[],
        document_quality={},
        drug_interaction_checked=False,
        escalation_flags=[],
        escalations=[],
        needs_escalation=False,
        escalation_done=False,
        escalation_message="",
        escalation_type="",
        escalation_severity="high",
        open_flags=[],
        draft=None,
        draft_built=False,
        draft_validated=False,
        validation_issues=[],
        iteration_count=0,
        finished=False,
    )
