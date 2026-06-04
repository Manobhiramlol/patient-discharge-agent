"""Medication reconciliation: admission vs discharge with change flags."""

from __future__ import annotations

import re
from typing import Any

from agent.schema import MedicationEntry


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.lower().strip())


def reconcile_medications(
    admission: list[dict[str, str]],
    discharge: list[dict[str, str]],
) -> tuple[list[MedicationEntry], str]:
    """
    Compare admission and discharge med lists. Flag changes without documented reason.
    """
    adm_map = {_normalize_name(m.get("name", m.get("raw", ""))): m for m in admission}
    dis_map = {_normalize_name(m.get("name", m.get("raw", ""))): m for m in discharge}
    all_names = sorted(set(adm_map) | set(dis_map))

    entries: list[MedicationEntry] = []
    flags_summary: list[str] = []

    for norm in all_names:
        a = adm_map.get(norm)
        d = dis_map.get(norm)
        name = (d or a or {}).get("name", norm)
        on_adm = a is not None
        on_dis = d is not None

        change_type: str | None = None
        med_flags: list[str] = []
        reason: str | None = None

        if on_adm and on_dis:
            dose_a = (a or {}).get("dose", "")
            dose_d = (d or {}).get("dose", "")
            if dose_a and dose_d and dose_a != dose_d:
                change_type = "dose_changed"
            else:
                change_type = "unchanged"
            reason = (d or {}).get("documented_reason") or (a or {}).get(
                "documented_reason"
            )
        elif on_adm and not on_dis:
            change_type = "discontinued"
            reason = (a or {}).get("documented_reason")
            if not reason:
                med_flags.append("DISCONTINUED_WITHOUT_DOCUMENTED_REASON")
                flags_summary.append(f"{name}: discontinued without documented reason")
        elif not on_adm and on_dis:
            change_type = "new"
            reason = (d or {}).get("documented_reason")
            if not reason:
                med_flags.append("NEW_MED_WITHOUT_DOCUMENTED_REASON")
                flags_summary.append(f"{name}: new at discharge without documented reason")

        if change_type in ("dose_changed",) and not (d or {}).get("documented_reason"):
            med_flags.append("DOSE_CHANGE_WITHOUT_DOCUMENTED_REASON")
            flags_summary.append(f"{name}: dose changed without documented reason")

        source_file = (d or a or {}).get("source_file")
        source_page = (d or a or {}).get("source_page")
        source_note = (d or a or {}).get("source_note")

        entries.append(
            MedicationEntry(
                name=name,
                dose=(d or a or {}).get("dose"),
                frequency=(d or a or {}).get("frequency"),
                admission=on_adm,
                discharge=on_dis,
                change_type=change_type,
                documented_reason=reason,
                flags=med_flags,
                source_file=source_file,
                source_page=int(source_page) if source_page is not None else None,
                source_note=source_note,
            )
        )

    note = (
        "Medication reconciliation performed against admission and discharge lists in source notes."
    )
    if flags_summary:
        note += " FLAGGED: " + "; ".join(flags_summary)
    return entries, note
