"""Correction memory — lightweight learning from reviewer edits (cold-start friendly)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CorrectionMemory:
    """
    Stores patterns from (draft, edited) pairs.
    Justification: bandit/DPO need volume; memory gives immediate, interpretable
    improvements without training infra. Limitation: can overfit edit patterns.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, Any] = {"patterns": [], "version": 1}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))

    def learn_from_pair(
        self, patient_id: str, edit_log: list[str], match_rate: float
    ) -> None:
        self.data["patterns"].append(
            {
                "patient_id": patient_id,
                "edit_log": edit_log,
                "section_match_rate_before": match_rate,
            }
        )
        self.save()

    def suggest_flags(self) -> list[str]:
        """Apply learned hints to future drafts (conservative)."""
        hints: list[str] = []
        patterns = self.data.get("patterns", [])
        if any("principal_diagnosis" in str(p) for p in patterns):
            hints.append(
                "MEMORY: verify principal diagnosis when only secondary listed"
            )
        if any("pharmacist" in str(p) for p in patterns):
            hints.append("MEMORY: route med-flagged charts to pharmacist review")
        return hints

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
