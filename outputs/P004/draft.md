# Discharge Summary DRAFT — P004

> **DRAFT FOR CLINICIAN REVIEW — Do not use for clinical decisions without verification.**

## Review flags
- NEW_MED_WITHOUT_DOCUMENTED_REASON
- CLINICAL_CONFLICT
- DRAFT — requires clinician sign-off
- 2 conflict(s) require resolution

## Patient demographics
**Name:** Thomas Wright
  - Source: nursing_assessment.pdf, p.1
**Mrn:** SYN-1004
  - Source: nursing_assessment.pdf, p.1

## Admission & discharge dates
**Admission:** 2026-05-01
  - Source: nursing_assessment.pdf, p.1
**Discharge:** 2026-05-05
  - Source: physician_note.pdf, p.1

## Diagnoses
**Principal:** Cellulitis left leg
  - Source: nursing_assessment.pdf, p.1

## Hospital course
**Course:** IV vancomycin and ceftriaxone. Improved.
  - Source: physician_note.pdf, p.1

## Procedures
- MISSING — not documented in source notes

## Discharge medications (vs admission)
*Medication reconciliation performed against admission and discharge lists in source notes. FLAGGED: Cephalexin: new at discharge without documented reason*

- **Cephalexin** (new) — not on admission, discharge
- Dose: 500 mg  four times daily for 7 days
  - Reason: [NOT DOCUMENTED]
  - Flag: NEW_MED_WITHOUT_DOCUMENTED_REASON

## Allergies
**Allergy:** NKDA
  - Source: nursing_assessment.pdf, p.1
  - Flag: CONFLICTING_SOURCES
**Allergy:** Sulfa drugs — hives
  - Source: physician_note.pdf, p.1
  - Flag: CONFLICTING_SOURCES

## Follow-up instructions
**Follow-up:** PCP in 7 days
  - Source: physician_note.pdf, p.1

## Pending results
- NONE — no pending results documented in source notes

## Discharge condition
**Condition:** Afebrile, erythema resolved
  - Source: physician_note.pdf, p.1

## Conflicts Requiring Clinician Review
- Allergy list discrepancy between nursing (NKDA) and physician (sulfa) (sources: nursing_assessment.pdf, physician_note.pdf)
- Conflicting allergy documentation across notes: nkda | vs | sulfa drugs — hives (sources: nursing_assessment.pdf, physician_note.pdf)

## Safety escalations
- Allergy list discrepancy between nursing (NKDA) and physician (sulfa)
- Med reconciliation flag: Cephalexin