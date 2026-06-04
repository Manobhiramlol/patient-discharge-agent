"""Agent planner: LLM when configured, else replanning rule engine based on state gaps."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from agent.state import AgentState


@dataclass
class PlanDecision:
    reasoning: str
    action: str
    tool: str | None
    tool_input: dict[str, Any]
    next_hint: str


class Planner:
    """Decides next step from AgentState — supports OpenAI or deterministic replanning."""

    def __init__(self) -> None:
        self._api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self._model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    @property
    def uses_llm(self) -> bool:
        return bool(self._api_key)

    def decide(self, state: AgentState) -> PlanDecision:
        if self.uses_llm:
            llm_dec = self._llm_decide(state)
            if llm_dec:
                return llm_dec
        return self._rule_decide(state)

    def _rule_decide(self, state: AgentState) -> PlanDecision:
        """
        Dynamic replanning: branch on missing_fields, conflicts, med flags, PDF failures.
        Order is NOT fixed Node1→Node2→Node3 — gates re-evaluated each iteration.
        """
        pdfs = state.get("pdf_paths", [])
        read = set(state.get("corpus", {}).keys())
        unread = [p for p in pdfs if os.path.basename(p) not in read]

        missing = state.get("missing_fields", [])
        facts = state.get("validated_facts") or state.get("extracted_facts") or {}
        allergy_signal = _allergy_conflict_likely(facts)
        med_flags = any(getattr(m, "flags", None) for m in state.get("med_entries", []))
        pdf_failed = bool(state.get("pdf_failures"))

        if unread:
            target = unread[0]
            return PlanDecision(
                reasoning=(
                    f"{len(unread)} PDF(s) unread; ingestion required before synthesis. "
                    f"Missing fields so far: {missing or 'none yet'}."
                ),
                action="read_pdf",
                tool="pdf_read",
                tool_input={"path": target},
                next_hint="Re-assess missing_fields after extraction",
            )

        if pdf_failed and not state.get("facts_extracted") and state.get("corpus"):
            return PlanDecision(
                reasoning=(
                    "PDF_EXTRACTION_FAILED on one or more files; proceeding with partial corpus "
                    "and flagging incomplete sections."
                ),
                action="extract_facts",
                tool="fact_extractor",
                tool_input={"sources": list(state.get("corpus", {}).keys()), "partial": True},
                next_hint="Validate partial facts and surface gaps",
            )

        if not state.get("facts_extracted"):
            if not state.get("corpus"):
                return PlanDecision(
                    reasoning="No readable PDF text; cannot extract — will emit flagged draft.",
                    action="build_draft",
                    tool="draft_builder",
                    tool_input={"reason": "no_corpus"},
                    next_hint="Validate minimal draft",
                )
            return PlanDecision(
                reasoning="Corpus available; extract structured facts before clinical synthesis.",
                action="extract_facts",
                tool="fact_extractor",
                tool_input={"sources": list(state.get("corpus", {}).keys())},
                next_hint="Validate extracted facts",
            )

        if not state.get("facts_validated"):
            return PlanDecision(
                reasoning=(
                    f"Extracted facts need validation. Anticipated gaps: {missing or 'computing'}."
                ),
                action="validate_facts",
                tool="fact_validator",
                tool_input={},
                next_hint="Branch on missing_fields and conflict signals",
            )

        if allergy_signal and not state.get("conflicts_checked"):
            return PlanDecision(
                reasoning=(
                    "Allergy documentation conflict signal detected — "
                    "prioritizing conflict detection before medication reconciliation."
                ),
                action="detect_conflicts",
                tool="conflict_detector",
                tool_input={"priority": "allergy"},
                next_hint="Reconcile meds or escalate based on conflict result",
            )

        if (
            not state.get("meds_reconciled")
            and (facts.get("admission_medications") or facts.get("discharge_medications"))
        ):
            return PlanDecision(
                reasoning=(
                    "Medication lists present but not reconciled; "
                    f"missing_fields={ [m for m in missing if 'med' in m] or 'none'}."
                ),
                action="reconcile_medications",
                tool="med_reconciliation",
                tool_input={},
                next_hint="Check interactions if discharge meds exist",
            )

        if med_flags and not state.get("drug_interaction_checked"):
            meds = [m.name for m in state.get("med_entries", []) if m.discharge or m.admission]
            if meds:
                return PlanDecision(
                    reasoning=(
                        "Med reconciliation flagged changes without documented reason; "
                        "running interaction check before escalation."
                    ),
                    action="drug_interaction_check",
                    tool="drug_interaction_lookup",
                    tool_input={"medications": meds},
                    next_hint="Escalate med safety issues",
                )

        if not state.get("drug_interaction_checked"):
            meds = [
                m.name
                for m in state.get("med_entries", [])
                if m.discharge or m.admission
            ]
            if meds:
                return PlanDecision(
                    reasoning="Discharge medication list assembled; run KNOWN_INTERACTIONS lookup.",
                    action="drug_interaction_check",
                    tool="drug_interaction_lookup",
                    tool_input={"medications": meds},
                    next_hint="Detect cross-note conflicts",
                )
            # No medications to check - skip interaction check
            # State will be set in _update_state_after_action when action executes

        if not state.get("conflicts_checked"):
            return PlanDecision(
                reasoning="Cross-source consistency check before draft assembly.",
                action="detect_conflicts",
                tool="conflict_detector",
                tool_input={},
                next_hint="Escalate safety issues then compose draft",
            )

        if state.get("needs_escalation") and not state.get("escalation_done"):
            return PlanDecision(
                reasoning="Unresolved safety signals; escalate per policy before draft completion.",
                action="escalate",
                tool="safety_escalation",
                tool_input={
                    "concern_type": state.get("escalation_type", "general"),
                    "message": state.get("escalation_message", "Safety review required"),
                    "severity": state.get("escalation_severity", "high"),
                },
                next_hint="Compose draft with escalation recorded",
            )

        if not state.get("draft_built"):
            return PlanDecision(
                reasoning=(
                    "Prerequisite checks complete; assemble draft from validated_facts only "
                    f"(missing: {missing or 'none'})."
                ),
                action="build_draft",
                tool="draft_builder",
                tool_input={},
                next_hint="Run final validation node",
            )

        if not state.get("draft_validated"):
            return PlanDecision(
                reasoning=(
                    "Final validation: required sections, unsupported claims, conflicts surfaced, "
                    "missing/pending marked."
                ),
                action="validate_draft",
                tool="draft_validator",
                tool_input={},
                next_hint="Terminate — draft ready for clinician review",
            )

        return PlanDecision(
            reasoning="Draft validated; no further actions within scope.",
            action="finish",
            tool=None,
            tool_input={},
            next_hint="End agent loop",
        )

    def _llm_decide(self, state: AgentState) -> PlanDecision | None:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self._api_key)
            summary = {
                "pdfs_total": len(state.get("pdf_paths", [])),
                "pdfs_read": list(state.get("corpus", {}).keys()),
                "facts_extracted": state.get("facts_extracted"),
                "facts_validated": state.get("facts_validated"),
                "missing_fields": state.get("missing_fields", []),
                "meds_reconciled": state.get("meds_reconciled"),
                "drug_interaction_checked": state.get("drug_interaction_checked"),
                "conflicts_checked": state.get("conflicts_checked"),
                "draft_built": state.get("draft_built"),
                "draft_validated": state.get("draft_validated"),
                "pdf_failures": state.get("pdf_failures", []),
                "escalation_flags": state.get("escalation_flags", []),
                "iteration_count": state.get("iteration_count"),
            }
            prompt = (
                "You are a discharge-summary agent planner. Choose ONE next action. "
                "Never fabricate clinical data. Available actions: read_pdf, extract_facts, "
                "validate_facts, reconcile_medications, drug_interaction_check, detect_conflicts, "
                "escalate, build_draft, validate_draft, finish. Respond JSON only: "
                '{"reasoning":"...","action":"...","tool":"...","tool_input":{}}'
            )
            resp = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(summary)},
                ],
                temperature=0.2,
                max_tokens=400,
                timeout=30.0,
            )
            text = resp.choices[0].message.content or ""
            start = text.find("{")
            end = text.rfind("}") + 1
            if start < 0 or end <= start:
                return None
            data = json.loads(text[start:end])
            return PlanDecision(
                reasoning=data.get("reasoning", "LLM plan"),
                action=data.get("action", "finish"),
                tool=data.get("tool"),
                tool_input=data.get("tool_input", {}),
                next_hint="LLM-directed step",
            )
        except Exception:
            return None


def _allergy_conflict_likely(facts: dict[str, Any]) -> bool:
    mentions = facts.get("allergy_mentions", [])
    if len(mentions) < 2:
        return False
    texts = {m.get("text", "").lower().strip() for m in mentions if isinstance(m, dict)}
    return len(texts) > 1
