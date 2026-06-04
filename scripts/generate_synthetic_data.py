"""Generate synthetic patient PDF source notes for the take-home dataset."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _write_pdf(path: Path, title: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    y = height - 72
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, title)
    y -= 24
    c.setFont("Helvetica", 10)
    for line in body.split("\n"):
        if y < 72:
            c.showPage()
            y = height - 72
            c.setFont("Helvetica", 10)
        # wrap long lines
        while len(line) > 90:
            c.drawString(72, y, line[:90])
            line = line[90:]
            y -= 14
        c.drawString(72, y, line)
        y -= 14
    c.save()


PATIENTS = {
    "P001": {
        "description": "Complete chart — straightforward case",
        "notes": {
            "admission_note.pdf": """HOSPITAL ADMISSION NOTE
PATIENT NAME: Jane Doe
DATE OF BIRTH: 1985-03-12
MRN: SYN-1001
SEX: F

ADMISSION DATE: 2026-05-10
PRINCIPAL DIAGNOSIS: Community-acquired pneumonia
SECONDARY DIAGNOSES:
- Type 2 diabetes mellitus

ADMISSION MEDICATIONS:
- Metformin 500 mg twice daily
- Lisinopril 10 mg daily

ALLERGIES: NKDA

HOSPITAL COURSE: Admitted for hypoxemia. IV antibiotics started. Improved over 4 days.

PROCEDURES:
- None

DISCHARGE CONDITION: Stable, ambulating independently
DISCHARGE DATE: 2026-05-14
""",
            "discharge_summary_source.pdf": """DISCHARGE PLANNING NOTE
PATIENT NAME: Jane Doe
MRN: SYN-1001

DISCHARGE DATE: 2026-05-14
PRINCIPAL DIAGNOSIS: Community-acquired pneumonia
SECONDARY DIAGNOSES:
- Type 2 diabetes mellitus

DISCHARGE MEDICATIONS:
- Metformin 500 mg twice daily
- Lisinopril 10 mg daily
- Amoxicillin 500 mg three times daily for 5 days reason: complete antibiotic course

FOLLOW-UP: Primary care in 1 week. Repeat chest X-ray if symptoms persist.

PENDING RESULTS:
- None

ALLERGIES: NKDA
""",
        },
    },
    "P002": {
        "description": "Pending labs explicitly listed",
        "notes": {
            "admission_note.pdf": """ADMISSION NOTE
PATIENT NAME: Robert Chen
DOB: 1972-08-21
MRN: SYN-1002
SEX: M
ADMISSION DATE: 2026-05-18
PRINCIPAL DIAGNOSIS: Acute kidney injury
ADMISSION MEDICATIONS:
- Amlodipine 5 mg daily
ALLERGIES: Penicillin — rash
HOSPITAL COURSE: Creatinine elevated. Fluids held. Nephrology consulted. Improvement noted but culture pending.
PENDING RESULTS:
- Urine culture — pending at discharge
- BMP repeat in 48h — pending
""",
            "discharge_orders.pdf": """DISCHARGE ORDERS
PATIENT NAME: Robert Chen
DISCHARGE DATE: 2026-05-22
DISCHARGE MEDICATIONS:
- Amlodipine 5 mg daily
DISCHARGE CONDITION: Improved, creatinine trending down
FOLLOW-UP: Nephrology clinic in 5 days
PENDING RESULTS:
- Urine culture final report pending
""",
        },
    },
    "P003": {
        "description": "Medication change without documented reason",
        "notes": {
            "admission_note.pdf": """ADMISSION
PATIENT NAME: Maria Lopez
MRN: SYN-1003
ADMISSION DATE: 2026-04-02
PRINCIPAL DIAGNOSIS: Atrial fibrillation with RVR
ADMISSION MEDICATIONS:
- Warfarin 5 mg daily
- Metoprolol 25 mg twice daily
ALLERGIES: NKDA
""",
            "discharge_meds.pdf": """DISCHARGE MEDICATION RECONCILIATION
PATIENT NAME: Maria Lopez
DISCHARGE DATE: 2026-04-06
DISCHARGE MEDICATIONS:
- Warfarin 5 mg daily
- Metoprolol 50 mg twice daily
- Aspirin 81 mg daily
DISCHARGE CONDITION: Rate controlled
FOLLOW-UP: Cardiology in 2 weeks
""",
        },
    },
    "P004": {
        "description": "Conflicting allergy documentation",
        "notes": {
            "nursing_assessment.pdf": """NURSING ADMISSION ASSESSMENT
PATIENT NAME: Thomas Wright
MRN: SYN-1004
ADMISSION DATE: 2026-05-01
ALLERGIES: NKDA
PRINCIPAL DIAGNOSIS: Cellulitis left leg
""",
            "physician_note.pdf": """ATTENDING NOTE
PATIENT NAME: Thomas Wright
ALLERGIES: Sulfa drugs — hives
HOSPITAL COURSE: IV vancomycin and ceftriaxone. Improved.
DOCUMENTED CONFLICT:
- Allergy list discrepancy between nursing (NKDA) and physician (sulfa)
DISCHARGE DATE: 2026-05-05
DISCHARGE MEDICATIONS:
- Cephalexin 500 mg four times daily for 7 days
DISCHARGE CONDITION: Afebrile, erythema resolved
FOLLOW-UP: PCP in 7 days
""",
        },
    },
    "P005": {
        "description": "Drug interaction risk — warfarin + aspirin",
        "notes": {
            "admission_note.pdf": """ADMISSION
PATIENT NAME: Evelyn Park
MRN: SYN-1005
ADMISSION DATE: 2026-05-25
PRINCIPAL DIAGNOSIS: NSTEMI
ADMISSION MEDICATIONS:
- Warfarin 3 mg daily
- Atorvastatin 40 mg nightly
ALLERGIES: Latex — itching
""",
            "discharge_note.pdf": """DISCHARGE NOTE
PATIENT NAME: Evelyn Park
DISCHARGE DATE: 2026-05-28
DISCHARGE MEDICATIONS:
- Warfarin 3 mg daily
- Atorvastatin 40 mg nightly
- Aspirin 81 mg daily reason: secondary prevention post NSTEMI
DISCHARGE CONDITION: Stable for discharge
FOLLOW-UP: Cardiology in 3 days — bring medication list
SECONDARY DIAGNOSES:
- Coronary artery disease
""",
        },
    },
}


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data" / "patients"
    for pid, spec in PATIENTS.items():
        for filename, body in spec["notes"].items():
            path = data_dir / pid / filename
            _write_pdf(path, f"Synthetic — {pid} — {filename}", body.strip())
            print(f"Wrote {path}")
    print(f"\nGenerated {len(PATIENTS)} patients under {data_dir}")


if __name__ == "__main__":
    main()
