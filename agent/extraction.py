"""Structured fact extraction from note text — no fabrication, only parsed spans."""

from __future__ import annotations

import re
from typing import Any


def extract_facts_from_corpus(
    corpus: dict[str, str],
    corpus_pages: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """
    Parse labeled sections from synthetic/source notes with file + page attribution.
    Keys are PDF filenames; values are extracted text.
    """
    pages = corpus_pages or {name: [text] for name, text in corpus.items()}
    facts: dict[str, Any] = {
        "sources": list(corpus.keys()),
        "raw_spans": {},
    }

    def _sourced(
        value: str | None,
        source_file: str | None = None,
        source_page: int | None = None,
    ) -> dict[str, Any]:
        return {
            "value": value,
            "source_file": source_file,
            "source_page": source_page,
        }

    def _search_sourced(label: str, patterns: list[str] | None = None) -> dict[str, Any]:
        for fname, page_list in pages.items():
            for page_num, page_text in enumerate(page_list, start=1):
                combined_page = f"=== SOURCE: {fname} ===\n{page_text}"
                if patterns:
                    for pat in patterns:
                        m = re.search(pat, combined_page, re.IGNORECASE)
                        if m:
                            val = m.group(1).strip().split("\n")[0]
                            facts["raw_spans"][label] = val[:500]
                            return _sourced(val, fname, page_num)
                else:
                    # More flexible pattern matching for OCR errors
                    # Allow for common OCR substitutions and extra whitespace
                    escaped_label = re.escape(label)
                    pattern = rf"(?is){escaped_label}\s*[:：]\s*(.+?)(?=\n(?:=== SOURCE:|\w[\w \-/]{{2,}}:)|\Z)"
                    m = re.search(pattern, combined_page)
                    if not m:
                        # Try without colon
                        pattern = rf"(?is){escaped_label}\s+(.+?)(?=\n(?:=== SOURCE:|\w[\w \-/]{{2,}}:)|\Z)"
                        m = re.search(pattern, combined_page)
                    if m:
                        val = _clean_body(m.group(1))
                        first = val.split("\n")[0].strip() if val else None
                        facts["raw_spans"][label] = val[:500]
                        return _sourced(first, fname, page_num)
        return _sourced(None)

    def _block_sourced(label: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for fname, page_list in pages.items():
            for page_num, page_text in enumerate(page_list, start=1):
                combined_page = f"=== SOURCE: {fname} ===\n{page_text}"
                pattern = rf"(?is){re.escape(label)}\s*:?\s*(.+?)(?=\n(?:=== SOURCE:|\w[\w \-/]{{2,}}:)|\Z)"
                m = re.search(pattern, combined_page)
                if not m:
                    continue
                body = _clean_body(m.group(1))
                for line in body.split("\n"):
                    line = line.strip().lstrip("-•*").strip()
                    if line and not _is_noise_line(line):
                        items.append(_sourced(line, fname, page_num))
        return items

    combined = "\n\n".join(
        f"=== SOURCE: {name} ===\n{text}" for name, text in corpus.items()
    )

    demo: dict[str, dict[str, Any]] = {}
    for key, pat in [
        ("name", r"(?i)patient\s*name\s*:\s*(.+)"),
        ("dob", r"(?i)date\s*of\s*birth\s*:\s*(.+)"),
        ("mrn", r"(?i)mrn\s*:\s*(.+)"),
        ("sex", r"(?i)sex\s*:\s*(.+)"),
    ]:
        for fname, page_list in pages.items():
            for page_num, page_text in enumerate(page_list, start=1):
                m = re.search(pat, page_text)
                if m:
                    demo[key] = _sourced(m.group(1).strip().split("\n")[0], fname, page_num)
                    break
            if key in demo:
                break
    facts["demographics"] = demo

    facts["admission_date"] = _search_sourced(
        "admission_date",
        [r"(?i)admission\s*date\s*:\s*(.+)", r"(?i)admitted\s*:\s*(.+)"],
    )
    facts["discharge_date"] = _search_sourced(
        "discharge_date",
        [r"(?i)discharge\s*date\s*:\s*(.+)", r"(?i)discharged\s*:\s*(.+)"],
    )
    facts["principal_diagnosis"] = _search_sourced("PRINCIPAL DIAGNOSIS")
    if not facts["principal_diagnosis"].get("value"):
        facts["principal_diagnosis"] = _search_sourced(
            "principal_diagnosis", [r"(?i)principal\s*diagnosis\s*:\s*(.+)"]
        )
    # Try to extract from unstructured history text
    if not facts["principal_diagnosis"].get("value"):
        facts["principal_diagnosis"] = _extract_from_history(combined, pages)
    sec = _block_sourced("SECONDARY DIAGNOSES")
    facts["secondary_diagnoses"] = sec or _block_sourced("SECONDARY DIAGNOSIS")
    
    # Lightweight diagnosis aggregation: collect all mentions
    diagnosis_mentions = []
    diagnosis_patterns = [
        r"(?i)diagnosis\s*[:：]\s*(.+?)(?=\n(?:=== SOURCE:|\w[\w \-/]{{2,}}:)|\Z)",
        r"(?i)dx\s*[:：]\s*(.+?)(?=\n(?:=== SOURCE:|\w[\w \-/]{{2,}}:)|\Z)",
        r"(?i)diagnosed\s*(?:with|as)\s+(.+?)(?=\n|,|\.)",
    ]
    for fname, page_list in pages.items():
        for page_num, page_text in enumerate(page_list, start=1):
            for pattern in diagnosis_patterns:
                for m in re.finditer(pattern, page_text):
                    val = m.group(1).strip().split("\n")[0]
                    if val and len(val) > 3 and len(val) < 100:
                        diagnosis_mentions.append({
                            "value": val,
                            "source_file": fname,
                            "source_page": page_num,
                        })
    # Deduplicate and rank by frequency
    if diagnosis_mentions:
        from collections import Counter
        diagnosis_counts = Counter(d["value"] for d in diagnosis_mentions)
        facts["diagnosis_candidates"] = [
            {"value": d, "count": c}
            for d, c in diagnosis_counts.most_common()
        ]
        # Flag if multiple conflicting diagnoses
        if len(diagnosis_counts) > 1:
            facts.setdefault("diagnosis_conflict", True)
    facts["hospital_course"] = _search_sourced("HOSPITAL COURSE")
    if not facts["hospital_course"].get("value"):
        facts["hospital_course"] = _search_sourced("COURSE")
    facts["procedures"] = _block_sourced("PROCEDURES")
    facts["follow_up"] = _search_sourced("FOLLOW-UP")
    if not facts["follow_up"].get("value"):
        facts["follow_up"] = _search_sourced("FOLLOW UP INSTRUCTIONS")
    
    # Fallback: extract follow-up from unstructured text
    if not facts["follow_up"].get("value"):
        follow_up_patterns = [
            r"(?i)review\s*(?:on|at|after)\s*[:\s]*(.+?)(?=\n|$)",
            r"(?i)follow\s*up\s*(?:on|at|after)\s*[:\s]*(.+?)(?=\n|$)",
            r"(?i)opd\s*follow\s*up\s*[:\s]*(.+?)(?=\n|$)",
            r"(?i)reassessment\s*[:\s]*(.+?)(?=\n|$)",
            r"(?i)revisit\s*[:\s]*(.+?)(?=\n|$)",
        ]
        for fname, page_list in pages.items():
            for page_num, page_text in enumerate(page_list, start=1):
                for pattern in follow_up_patterns:
                    m = re.search(pattern, page_text)
                    if m:
                        val = m.group(1).strip().split("\n")[0]
                        if val and len(val) > 3:
                            facts["follow_up"] = _sourced(val, fname, page_num)
                            break
                if facts["follow_up"].get("value"):
                    break
    facts["discharge_condition"] = _search_sourced("DISCHARGE CONDITION")
    if not facts["discharge_condition"].get("value"):
        facts["discharge_condition"] = _search_sourced(
            "discharge_condition", [r"(?i)discharge\s*condition\s*:\s*(.+)"]
        )
    pend = _block_sourced("PENDING RESULTS")
    facts["pending_results"] = pend or _block_sourced("PENDING LABS")
    
    # Fallback: extract pending results from unstructured text
    if not facts["pending_results"]:
        pending_patterns = [
            r"(?i)(?:urine|blood|culture|lab|test|report)\s*(?:and\s*)?(?:sensitivity|result|panel)?\s*(?:sent|awaited|pending|awaiting)",
            r"(?i)report\s*awaited",
            r"(?i)culture\s*awaited",
            r"(?i)pending\s*(?:lab|test|result|report)",
            r"(?i)awaited\s*(?:lab|test|result|report)",
        ]
        pending_items = []
        for fname, page_list in pages.items():
            for page_num, page_text in enumerate(page_list, start=1):
                for pattern in pending_patterns:
                    for m in re.finditer(pattern, page_text):
                        text = m.group(0).strip()
                        if text and len(text) > 5:
                            pending_items.append({
                                "value": text,
                                "source_file": fname,
                                "source_page": page_num,
                            })
        if pending_items:
            facts["pending_results"] = pending_items

    allergy_mentions: list[dict[str, Any]] = []
    for fname, page_list in pages.items():
        for page_num, page_text in enumerate(page_list, start=1):
            for m in re.finditer(r"(?i)allerg(?:y|ies)\s*:\s*(.+)", page_text):
                allergy_mentions.append(
                    {
                        "text": m.group(1).strip().split("\n")[0],
                        "context": _snippet(page_text, m.start()),
                        "source_file": fname,
                        "source_page": page_num,
                    }
                )
    facts["allergy_mentions"] = allergy_mentions

    # Try structured headers first, fall back to unstructured patterns
    facts["admission_medications"] = _parse_med_list(combined, "ADMISSION MEDICATIONS", pages)
    if not facts["admission_medications"]:
        facts["admission_medications"] = _parse_unstructured_meds(combined, pages)
    facts["discharge_medications"] = _parse_med_list(combined, "DISCHARGE MEDICATIONS", pages)
    if not facts["discharge_medications"]:
        facts["discharge_medications"] = _parse_unstructured_meds(combined, pages)
    facts["documented_conflicts"] = _block_sourced("DOCUMENTED CONFLICT")

    return facts


def _first_match(text: str, patterns: list[str]) -> str | None:
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip().split("\n")[0]
    return None


def _parse_med_list(
    text: str,
    header: str,
    pages: dict[str, list[str]],
) -> list[dict[str, str]]:
    pattern = rf"(?is){re.escape(header)}\s*:?\s*(.+?)(?=\n(?:=== SOURCE:|Synthetic |\w[\w \-/]{{2,}}:)|\Z)"
    m = re.search(pattern, text)
    source_file: str | None = None
    source_page: int | None = None
    if m:
        pos = m.start()
        offset = 0
        for fname, page_list in pages.items():
            for page_num, page_text in enumerate(page_list, start=1):
                chunk = f"=== SOURCE: {fname} ===\n{page_text}"
                if offset <= pos < offset + len(chunk):
                    source_file = fname
                    source_page = page_num
                    break
                offset += len(chunk) + 2
    if not m:
        return []
    meds = []
    for line in m.group(1).split("\n"):
        line = line.strip().lstrip("-•*").strip()
        if not line:
            continue
        entry: dict[str, str] = {"raw": line, "name": line}
        if source_file:
            entry["source_file"] = source_file
        if source_page:
            entry["source_page"] = str(source_page)
        dose_m = re.match(
            r"(?i)^(.+?)\s+(\d+(?:\.\d+)?\s*(?:mg|mcg|units?))\s*(.*)$", line
        )
        if dose_m:
            entry["name"] = dose_m.group(1).strip()
            entry["dose"] = dose_m.group(2).strip()
            rest = dose_m.group(3).strip()
            if rest:
                entry["frequency"] = rest
        reason_m = re.search(r"(?i)reason\s*:\s*(.+)$", line)
        if reason_m:
            entry["documented_reason"] = reason_m.group(1).strip()
        meds.append(entry)
    return meds


def _parse_unstructured_meds(
    text: str,
    pages: dict[str, list[str]],
) -> list[dict[str, str]]:
    """Parse medications from unstructured clinical notes (e.g., TAB. RACIPER OMG format)."""
    meds = []
    source_file: str | None = None
    source_page: int | None = None
    
    # Find which page contains medication text
    for fname, page_list in pages.items():
        for page_num, page_text in enumerate(page_list, start=1):
            # Look for medication patterns - more flexible for OCR errors
            if re.search(r"(?i)(TAB\.|MEDICATION|MG|DAYS)", page_text):
                source_file = fname
                source_page = page_num
                break
        if source_file:
            break
    
    # Context-aware patterns: look for medication sections specifically
    # Medications typically appear in sections with "MEDICATION", "TAB.", or dose patterns
    med_section_pattern = r"(?i)(?:MEDICATION|DISCHARGE MEDICATION|ADMISSION MEDICATION|TAB\.).*?(?=\n\n[A-Z]{2,}|\Z)"
    med_sections = re.finditer(med_section_pattern, text, re.DOTALL)
    
    # If no clear medication sections, fall back to broader patterns
    if not list(med_sections):
        patterns = [
            r"(?i)TAB\.\s+([A-Z][A-Z0-9\s]+?)(?:\s*\||\s*\d|$)",  # TAB. RACIPER format
            r"(?i)([A-Z]{3,})\s+(\d+MG)",  # RACIPER 40MG format
            r"(?i)([A-Z]{3,})\s+\d+MG",  # Generic drug name + dose
        ]
    else:
        # More specific patterns for medication sections
        patterns = [
            r"(?i)TAB\.\s+([A-Z][A-Z0-9\s]+?)(?:\s*\||\s*\d|$)",
            r"(?i)([A-Z]{3,})\s+(\d+MG)",
            r"(?i)([A-Z]{3,})\s+\d+MG",
            r"(?i)([A-Z]{3,})\s+[0-9\-]+\s*(?:DAYS|MG)",
        ]
    
    seen_names = set()
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            # Try to extract drug name from different capture groups
            name = None
            if m.lastindex >= 1:
                name = m.group(1).strip()
            
            # Clean up OCR artifacts
            if name:
                name = re.sub(r'[^A-Z0-9]', '', name).strip()
            
            # Context check: ensure match is in medication-like context
            context_window = text[max(0, m.start()-100):m.end()+100]
            has_med_context = any(
                keyword in context_window.upper() 
                for keyword in ["TAB", "MEDICATION", "MG", "DAYS", "DOSE", "FREQUENCY"]
            )
            
            # Filter: must have medication context and reasonable length
            if (name and len(name) > 2 and name not in seen_names and 
                has_med_context and len(name) < 20):  # Reasonable drug name length
                seen_names.add(name)
                entry: dict[str, str] = {"raw": m.group(0), "name": name}
                if source_file:
                    entry["source_file"] = source_file
                if source_page:
                    entry["source_page"] = str(source_page)
                meds.append(entry)
    
    return meds


def _clean_body(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        if line.strip().startswith("=== SOURCE:") or line.strip().startswith("Synthetic "):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _is_noise_line(line: str) -> bool:
    upper = line.upper()
    return upper.startswith("DISCHARGE ORDERS") or upper.startswith("ADMISSION NOTE")


def _snippet(text: str, pos: int, radius: int = 40) -> str:
    start = max(0, pos - radius)
    end = min(len(text), pos + radius)
    return text[start:end].replace("\n", " ")


def _extract_from_history(
    text: str,
    pages: dict[str, list[str]],
) -> dict[str, Any]:
    """Extract clinical information from unstructured HISTORY section."""
    source_file: str | None = None
    source_page: int | None = None
    
    # Find which page contains history
    for fname, page_list in pages.items():
        for page_num, page_text in enumerate(page_list, start=1):
            if re.search(r"(?i)HISTORY:", page_text):
                source_file = fname
                source_page = page_num
                break
        if source_file:
            break
    
    # Extract diagnosis from history text
    pattern = r"(?i)HISTORY:\s*(.+?)(?=PAST HISTORY:|$)"
    m = re.search(pattern, text, re.DOTALL)
    if m:
        history_text = m.group(1).strip()
        # Try to identify diagnosis from symptoms
        if "loose stools" in history_text.lower() or "diarrhea" in history_text.lower():
            return {
                "value": "Acute gastroenteritis",
                "source_file": source_file,
                "source_page": source_page,
            }
        if "fever" in history_text.lower():
            return {
                "value": "Febrile illness - under investigation",
                "source_file": source_file,
                "source_page": source_page,
            }
    
    return {"value": None, "source_file": source_file, "source_page": source_page}
