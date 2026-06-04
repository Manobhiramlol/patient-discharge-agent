"""Structured discharge draft schema — all fields support explicit missing/pending markers."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FieldStatus(str, Enum):
    DOCUMENTED = "documented"
    MISSING = "missing"
    PENDING = "pending"
    CONFLICT = "conflict"
    NEEDS_REVIEW = "needs_review"


MISSING_DISPLAY = "MISSING — not documented in source notes"


class SourcedValue(BaseModel):
    value: str | None = None
    status: FieldStatus = FieldStatus.MISSING
    source_file: str | None = None
    page: int | None = None
    source_note: str | None = None
    evidence: str | None = None
    flags: list[str] = Field(default_factory=list)

    def evidence_line(self) -> str | None:
        if self.source_file:
            page = f", p.{self.page}" if self.page else ""
            return f"Source: {self.source_file}{page}"
        return None


class MedicationEntry(BaseModel):
    name: str
    dose: str | None = None
    route: str | None = None
    frequency: str | None = None
    admission: bool = False
    discharge: bool = False
    change_type: str | None = None  # new, discontinued, dose_changed, unchanged
    documented_reason: str | None = None
    flags: list[str] = Field(default_factory=list)
    source_file: str | None = None
    source_page: int | None = None
    source_note: str | None = None


class DischargeDraft(BaseModel):
    """DRAFT discharge summary — clinician review required."""

    patient_id: str
    is_draft: bool = True
    review_banner: str = (
        "DRAFT FOR CLINICIAN REVIEW — Do not use for clinical decisions without verification."
    )

    demographics: dict[str, SourcedValue] = Field(default_factory=dict)
    admission_date: SourcedValue = Field(default_factory=SourcedValue)
    discharge_date: SourcedValue = Field(default_factory=SourcedValue)
    principal_diagnosis: SourcedValue = Field(default_factory=SourcedValue)
    secondary_diagnoses: list[SourcedValue] = Field(default_factory=list)
    hospital_course: SourcedValue = Field(default_factory=SourcedValue)
    procedures: list[SourcedValue] = Field(default_factory=list)
    discharge_medications: list[MedicationEntry] = Field(default_factory=list)
    medication_reconciliation_notes: str = ""
    allergies: list[SourcedValue] = Field(default_factory=list)
    follow_up_instructions: SourcedValue = Field(default_factory=SourcedValue)
    pending_results: list[SourcedValue] = Field(default_factory=list)
    discharge_condition: SourcedValue = Field(default_factory=SourcedValue)

    safety_escalations: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    global_flags: list[str] = Field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            f"# Discharge Summary DRAFT — {self.patient_id}",
            "",
            f"> **{self.review_banner}**",
            "",
        ]
        if self.global_flags:
            lines.append("## Review flags")
            for f in self.global_flags:
                lines.append(f"- {f}")
            lines.append("")

        def _display_value(sv: SourcedValue) -> str:
            if sv.value:
                return sv.value
            if sv.status == FieldStatus.MISSING:
                return MISSING_DISPLAY
            if sv.status == FieldStatus.PENDING:
                return "PENDING — explicitly marked pending in source notes"
            if sv.status == FieldStatus.CONFLICT:
                return "CONFLICT — conflicting documentation in source notes"
            return f"[{sv.status.value.upper()}]"

        def _sv(label: str, sv: SourcedValue) -> None:
            lines.append(f"**{label}:** {_display_value(sv)}")
            ev = sv.evidence_line()
            if ev:
                lines.append(f"  - {ev}")
            if sv.flags:
                for fl in sv.flags:
                    lines.append(f"  - Flag: {fl}")

        lines.append("## Patient demographics")
        for k, v in self.demographics.items():
            _sv(k.replace("_", " ").title(), v)
        lines.append("")
        lines.append("## Admission & discharge dates")
        _sv("Admission", self.admission_date)
        _sv("Discharge", self.discharge_date)
        lines.append("")
        lines.append("## Diagnoses")
        _sv("Principal", self.principal_diagnosis)
        for i, d in enumerate(self.secondary_diagnoses, 1):
            _sv(f"Secondary {i}", d)
        lines.append("")
        lines.append("## Hospital course")
        _sv("Course", self.hospital_course)
        lines.append("")
        lines.append("## Procedures")
        if not self.procedures:
            lines.append(f"- {MISSING_DISPLAY}")
        for p in self.procedures:
            _sv("Procedure", p)
        lines.append("")
        lines.append("## Discharge medications (vs admission)")
        if self.medication_reconciliation_notes:
            lines.append(f"*{self.medication_reconciliation_notes}*")
            lines.append("")
        for m in self.discharge_medications:
            adm = "admission" if m.admission else "not on admission"
            dis = "discharge" if m.discharge else "not at discharge"
            ch = m.change_type or "unknown"
            lines.append(f"- **{m.name}** ({ch}) — {adm}, {dis}")
            if m.dose:
                lines.append(f"  - Dose: {m.dose} {m.route or ''} {m.frequency or ''}".strip())
            if m.documented_reason:
                lines.append(f"  - Reason: {m.documented_reason}")
            elif m.flags:
                lines.append("  - Reason: [NOT DOCUMENTED]")
            if m.source_file:
                page = f", p.{m.source_page}" if m.source_page else ""
                lines.append(f"  - Source: {m.source_file}{page}")
            if m.source_note:
                lines.append(f"  - Note: {m.source_note}")
            for fl in m.flags:
                lines.append(f"  - Flag: {fl}")
        lines.append("")
        lines.append("## Allergies")
        if not self.allergies:
            lines.append(f"- {MISSING_DISPLAY}")
        for a in self.allergies:
            _sv("Allergy", a)
        lines.append("")
        lines.append("## Follow-up instructions")
        _sv("Follow-up", self.follow_up_instructions)
        lines.append("")
        lines.append("## Pending results")
        if not self.pending_results:
            lines.append("- NONE — no pending results documented in source notes")
        for pr in self.pending_results:
            _sv("Pending", pr)
        lines.append("")
        lines.append("## Discharge condition")
        _sv("Condition", self.discharge_condition)

        if self.conflicts:
            lines.append("")
            lines.append("## Conflicts Requiring Clinician Review")
            for c in self.conflicts:
                desc = c.get("description", c)
                src = c.get("sources")
                line = f"- {desc}"
                if src:
                    line += f" (sources: {', '.join(src)})"
                lines.append(line)

        if self.safety_escalations:
            lines.append("")
            lines.append("## Safety escalations")
            for e in self.safety_escalations:
                lines.append(f"- {e.get('message', e)}")

        return "\n".join(lines)
