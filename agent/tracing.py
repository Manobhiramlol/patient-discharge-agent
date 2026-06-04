"""Step-by-step observability trace."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class TraceStep:
    step: int
    reasoning: str
    action: str
    tool: str | None
    inputs: dict[str, Any]
    result: Any
    next_decision: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if isinstance(d.get("result"), (dict, list, str, int, float, bool, type(None))):
            return d
        d["result"] = str(d["result"])
        return d


class TraceLogger:
    def __init__(self, patient_id: str) -> None:
        self.patient_id = patient_id
        self.steps: list[TraceStep] = []
        self._counter = 0

    def log(
        self,
        reasoning: str,
        action: str,
        tool: str | None,
        inputs: dict[str, Any],
        result: Any,
        next_decision: str,
    ) -> None:
        self._counter += 1
        self.steps.append(
            TraceStep(
                step=self._counter,
                reasoning=reasoning,
                action=action,
                tool=tool,
                inputs=inputs,
                result=_truncate_result(result),
                next_decision=next_decision,
            )
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "patient_id": self.patient_id,
            "total_steps": len(self.steps),
            "steps": [s.to_dict() for s in self.steps],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _truncate_result(result: Any, max_len: int = 4000) -> Any:
    if isinstance(result, str) and len(result) > max_len:
        return result[:max_len] + f"\n... [truncated {len(result) - max_len} chars]"
    if isinstance(result, dict):
        return {k: _truncate_result(v, max_len // 2) for k, v in result.items()}
    return result
