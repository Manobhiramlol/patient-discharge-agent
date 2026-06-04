"""Core agent loop: plan → act → observe → replan with step cap and full tracing."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agent.conflicts import detect_conflicts
from agent.draft_builder import build_draft
from agent.extraction import extract_facts_from_corpus
from agent.med_reconciliation import reconcile_medications
from agent.mock_tools import escalate_safety_concern, lookup_drug_interactions
from agent.pdf_tools import list_patient_pdfs, read_pdf_text
from agent.planner import Planner
from agent.schema import DischargeDraft
from agent.state import AgentState, initial_state
from agent.tracing import TraceLogger
from agent.validation import validate_draft, validate_draft_strict, validate_extracted_facts

load_dotenv()

DEFAULT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "25"))


def run_agent(
    patient_id: str,
    data_root: Path,
    output_root: Path,
    max_steps: int | None = None,
) -> dict[str, Any]:
    max_steps = max_steps or DEFAULT_MAX_STEPS
    patient_dir = data_root / "patients" / patient_id
    out_dir = output_root / patient_id
    out_dir.mkdir(parents=True, exist_ok=True)

    trace = TraceLogger(patient_id)
    planner = Planner()

    # Support two layouts for test convenience:
    # 1) patient folder: data/patients/<patient_id>/*.pdf (default)
    # 2) single PDF file: data/patients/<patient_id>.pdf (convenience for single-file uploads)
    single_pdf = data_root / "patients" / f"{patient_id}.pdf"
    if single_pdf.exists():
        pdf_list = [str(single_pdf)]
    else:
        pdf_list = [str(p) for p in list_patient_pdfs(patient_dir)]

    state: AgentState = initial_state(
        patient_id,
        pdf_list,
    )

    draft: DischargeDraft | None = None
    step = 0

    while step < max_steps and not state.get("finished"):
        step += 1
        state["iteration_count"] = step
        decision = planner.decide(state)

        print(f"[STEP {step}] {decision.action}")

        if decision.action == "finish":
            trace.log(
                reasoning=decision.reasoning,
                action="finish",
                tool=None,
                inputs={},
                result={"status": "complete"},
                next_decision="exit",
            )
            state["finished"] = True
            break

        result = _execute_action(decision, state, patient_id, patient_dir)
        _update_state_after_action(decision.action, result, state)

        # Log escalation events
        if decision.action == "escalate" or state.get("needs_escalation"):
            print(f"[ESCALATION] {state.get('escalation_message', 'Safety review required')}")

        trace.log(
            reasoning=decision.reasoning,
            action=decision.action,
            tool=decision.tool,
            inputs=decision.tool_input,
            result=result,
            next_decision=decision.next_hint,
        )

    if step >= max_steps and not state.get("draft_built"):
        trace.log(
            reasoning="Step cap reached before draft completion",
            action="abort_cap",
            tool=None,
            inputs={"max_steps": max_steps},
            result={"error": "STEP_CAP_EXCEEDED"},
            next_decision="emit partial draft with cap flag",
        )
        state.setdefault("open_flags", []).append(f"AGENT_STEP_CAP_REACHED ({max_steps})")
        draft = _force_build_draft(state)
        draft.global_flags.append("PARTIAL_DRAFT_STEP_CAP")

    if draft is None and state.get("draft"):
        draft = state["draft"]

    if draft is None:
        draft = DischargeDraft(
            patient_id=patient_id,
            global_flags=["AGENT_FAILED_TO_PRODUCE_DRAFT — manual chart review required"],
        )

    for issue in validate_draft(draft):
        flag = f"VALIDATION: {issue}"
        if flag not in draft.global_flags:
            draft.global_flags.append(flag)

    _write_outputs(out_dir, draft, trace)
    return {
        "patient_id": patient_id,
        "steps": step,
        "output_dir": str(out_dir),
        "draft_path": str(out_dir / "draft.json"),
        "trace_path": str(out_dir / "trace.json"),
        "flags": draft.global_flags,
    }


def _force_build_draft(state: AgentState) -> DischargeDraft:
    if not state.get("facts_extracted") and state.get("corpus"):
        state["extracted_facts"] = extract_facts_from_corpus(
            state["corpus"], state.get("corpus_pages")
        )
        state["facts_extracted"] = True
    if state.get("extracted_facts") and not state.get("facts_validated"):
        validated, missing, _ = validate_extracted_facts(state["extracted_facts"])
        state["validated_facts"] = validated
        state["missing_fields"] = missing
        state["facts_validated"] = True
    facts = state.get("validated_facts") or state.get("extracted_facts") or {}
    if facts and not state.get("meds_reconciled"):
        entries, note = reconcile_medications(
            facts.get("admission_medications", []),
            facts.get("discharge_medications", []),
        )
        state["med_entries"] = entries
        state["med_note"] = note
        state["meds_reconciled"] = True
    if not state.get("conflicts_checked"):
        state["conflicts"] = detect_conflicts(facts)
        state["conflicts_checked"] = True
    return build_draft(
        state["patient_id"],
        facts,
        state.get("med_entries", []),
        state.get("med_note", ""),
        state.get("conflicts", []),
        state.get("escalations", []),
        state.get("pdf_failures", []),
    )


def _execute_action(
    decision: Any,
    state: AgentState,
    patient_id: str,
    patient_dir: Path,
) -> Any:
    action = decision.action

    if action == "read_pdf":
        path_str = decision.tool_input.get("path", "")
        path = Path(path_str)
        if not path.is_absolute():
            path = patient_dir / path.name
        return read_pdf_text(path)

    if action == "extract_facts":
        if not state.get("corpus"):
            return {"ok": False, "error": "no_corpus"}
        facts = extract_facts_from_corpus(state["corpus"], state.get("corpus_pages"))
        return {"ok": True, "fact_keys": list(facts.keys())}

    if action == "validate_facts":
        if not state.get("extracted_facts"):
            return {"ok": False, "error": "no_extracted_facts"}
        validated, missing, issues = validate_extracted_facts(state["extracted_facts"])
        return {"ok": True, "missing_fields": missing, "issues": issues}

    if action == "reconcile_medications":
        facts = state.get("validated_facts") or state.get("extracted_facts") or {}
        entries, note = reconcile_medications(
            facts.get("admission_medications", []),
            facts.get("discharge_medications", []),
        )
        return {"ok": True, "med_count": len(entries), "note": note}

    if action == "drug_interaction_check":
        meds = decision.tool_input.get("medications", [])
        return lookup_drug_interactions(meds)

    if action == "detect_conflicts":
        facts = state.get("validated_facts") or state.get("extracted_facts") or {}
        return {"ok": True, "conflicts": detect_conflicts(facts)}

    if action == "escalate":
        return escalate_safety_concern(
            concern_type=decision.tool_input.get("concern_type", "general"),
            message=decision.tool_input.get("message", "Review required"),
            severity=decision.tool_input.get("severity", "high"),
            patient_id=patient_id,
        )

    if action == "build_draft":
        return {"ok": True, "action": "build_draft"}

    if action == "validate_draft":
        if not state.get("draft"):
            return {"ok": False, "error": "no_draft"}
        ok, issues = validate_draft_strict(
            state["draft"], 
            state.get("missing_fields", []),
            state.get("validated_facts")
        )
        return {"ok": ok, "issues": issues}

    return {"ok": False, "error": f"unknown_action:{action}"}


def _update_state_after_action(action: str, result: Any, state: AgentState) -> None:
    if action == "read_pdf":
        if isinstance(result, dict) and result.get("ok"):
            fname = result.get("filename", Path(result["path"]).name)
            state.setdefault("corpus", {})[fname] = result["text"]
            state.setdefault("corpus_pages", {})[fname] = result.get("pages", [result["text"]])
            if isinstance(result.get("document_quality"), dict):
                state.setdefault("document_quality", {})[fname] = result["document_quality"]
                if result["document_quality"].get("low_confidence"):
                    state.setdefault("open_flags", []).append(
                        f"LOW_OCR_CONFIDENCE: {fname}"
                    )
        else:
            failure = result if isinstance(result, dict) else {"detail": str(result)}
            state.setdefault("pdf_failures", []).append(failure)
            if failure.get("flag") == "PDF_EXTRACTION_FAILED":
                state.setdefault("escalation_flags", []).append("PDF_EXTRACTION_FAILED")
                state.setdefault("open_flags", []).append(
                    f"PDF_EXTRACTION_FAILED: {failure.get('path', 'unknown')}"
                )

    elif action == "extract_facts":
        if isinstance(result, dict) and result.get("ok"):
            state["extracted_facts"] = extract_facts_from_corpus(
                state.get("corpus", {}), state.get("corpus_pages")
            )
            state["facts_extracted"] = True
            pending = state["extracted_facts"].get("pending_results", [])
            state["pending_results"] = [
                p.get("value") if isinstance(p, dict) else p for p in pending
            ]

    elif action == "validate_facts":
        if isinstance(result, dict) and result.get("ok"):
            validated, missing, issues = validate_extracted_facts(state["extracted_facts"])
            state["validated_facts"] = validated
            state["missing_fields"] = missing
            state["facts_validated"] = True
            if issues:
                state.setdefault("open_flags", []).extend(issues)

    elif action == "reconcile_medications":
        if isinstance(result, dict) and result.get("ok"):
            facts = state.get("validated_facts") or state.get("extracted_facts") or {}
            entries, note = reconcile_medications(
                facts.get("admission_medications", []),
                facts.get("discharge_medications", []),
            )
            state["med_entries"] = entries
            state["med_note"] = note
            state["meds_reconciled"] = True
            for e in entries:
                state.setdefault("open_flags", []).extend(e.flags)

    elif action == "drug_interaction_check":
        state["drug_interaction_checked"] = True
        if isinstance(result, dict):
            state["interactions"] = result.get("interactions", [])
            if state["interactions"]:
                state["needs_escalation"] = True
                state["escalation_type"] = "drug_interaction"
                state["escalation_message"] = "; ".join(
                    i["message"] for i in state["interactions"]
                )
                state.setdefault("escalation_flags", []).append("DRUG_INTERACTION_FOUND")
                state.setdefault("open_flags", []).append("DRUG_INTERACTION_FOUND")

    elif action == "detect_conflicts":
        state["conflicts_checked"] = True
        if isinstance(result, dict):
            state["conflicts"] = result.get("conflicts", [])
            if state["conflicts"]:
                state["needs_escalation"] = True
                state["escalation_type"] = "data_conflict"
                state["escalation_message"] = state["conflicts"][0].get(
                    "description", "Conflicting documentation"
                )
                state.setdefault("escalation_flags", []).append("CLINICAL_CONFLICT")
                state.setdefault("open_flags", []).append("CLINICAL_CONFLICT")

    elif action == "escalate":
        state["escalation_done"] = True
        if isinstance(result, dict) and result.get("ok"):
            state.setdefault("escalations", []).append(result)

    elif action == "build_draft":
        if state.get("needs_escalation") and not state.get("escalation_done"):
            esc = escalate_safety_concern(
                concern_type=state.get("escalation_type", "general"),
                message=state.get("escalation_message", "Safety review"),
                patient_id=state["patient_id"],
            )
            state.setdefault("escalations", []).append(esc)
            state["escalation_done"] = True

        for e in state.get("med_entries", []):
            if e.flags and not state.get("needs_escalation"):
                state["needs_escalation"] = True
                state["escalation_message"] = "Medication changes without documented reason"
                state["escalation_type"] = "med_reconciliation"
            if e.flags:
                esc = escalate_safety_concern(
                    concern_type="med_reconciliation",
                    message=f"Med reconciliation flag: {e.name}",
                    severity="medium",
                    patient_id=state["patient_id"],
                )
                state.setdefault("escalations", []).append(esc)

        facts = state.get("validated_facts") or state.get("extracted_facts") or {}
        draft = build_draft(
            state["patient_id"],
            facts,
            state.get("med_entries", []),
            state.get("med_note", ""),
            state.get("conflicts", []),
            state.get("escalations", []),
            state.get("pdf_failures", []),
        )
        for flag in state.get("open_flags", []):
            if flag not in draft.global_flags:
                draft.global_flags.insert(0, flag)
        state["draft"] = draft
        state["draft_built"] = True

    elif action == "validate_draft":
        if isinstance(result, dict):
            state["validation_issues"] = result.get("issues", [])
            state["draft_validated"] = result.get("ok", False)
            if state.get("draft") and state["validation_issues"]:
                for issue in state["validation_issues"]:
                    if issue not in state["draft"].global_flags:
                        state["draft"].global_flags.append(f"VALIDATION: {issue}")
            state["finished"] = True


def _write_outputs(out_dir: Path, draft: DischargeDraft, trace: TraceLogger) -> None:
    (out_dir / "draft.json").write_text(
        json.dumps(draft.model_dump(), indent=2), encoding="utf-8"
    )
    (out_dir / "draft.md").write_text(draft.to_markdown(), encoding="utf-8")
    trace.save(out_dir / "trace.json")
