"""Part 2 evaluation: simulated reviewer + before/after metrics."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from agent.schema import DischargeDraft
from learning.memory import CorrectionMemory
from learning.reviewer import SimulatedReviewer, section_match_rate


def evaluate(outputs_dir: Path, out_learning: Path) -> dict:
    reviewer = SimulatedReviewer()
    memory = CorrectionMemory(out_learning / "correction_memory.json")
    results = []

    for draft_path in sorted(outputs_dir.glob("*/draft.json")):
        patient_id = draft_path.parent.name
        draft = DischargeDraft.model_validate_json(draft_path.read_text(encoding="utf-8"))
        before = draft.model_dump()
        review = reviewer.edit(draft)
        edited = review["edited_draft"]
        rate_before = section_match_rate(before, edited)
        memory.learn_from_pair(patient_id, review["edit_log"], rate_before)

        pair_dir = out_learning / "pairs" / patient_id
        pair_dir.mkdir(parents=True, exist_ok=True)
        (pair_dir / "draft.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
        (pair_dir / "edited.json").write_text(json.dumps(edited, indent=2), encoding="utf-8")
        (pair_dir / "edit_log.json").write_text(
            json.dumps(review["edit_log"], indent=2), encoding="utf-8"
        )

        results.append(
            {
                "patient_id": patient_id,
                "section_match_rate": round(rate_before, 3),
                "edits": review["edit_log"],
            }
        )

    avg = sum(r["section_match_rate"] for r in results) / len(results) if results else 0
    metrics = {
        "patients": len(results),
        "mean_section_match_rate": round(avg, 3),
        "per_patient": results,
        "memory_hints": memory.suggest_flags(),
        "limitations": [
            "Cold start: memory empty until first evaluation pass",
            "Section match rate can be gamed by copying reviewer output",
            "Safety flags preserved but not used as reward — intentional",
        ],
    }
    out_learning.mkdir(parents=True, exist_ok=True)
    (out_learning / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    outputs = root / "outputs"
    out_learning = root / "outputs" / "learning"
    if not outputs.exists():
        print("Run agent first: python -m agent run-all", file=sys.stderr)
        return 1
    metrics = evaluate(outputs, out_learning)
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
