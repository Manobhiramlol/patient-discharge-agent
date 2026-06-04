# Discharge Summary DRAFT — P003

> **DRAFT FOR CLINICIAN REVIEW — Do not use for clinical decisions without verification.**

## Review flags
- DRUG_INTERACTION_FOUND
- DOSE_CHANGE_WITHOUT_DOCUMENTED_REASON
- NEW_MED_WITHOUT_DOCUMENTED_REASON
- DRAFT — requires clinician sign-off

## Patient demographics
**Name:** Maria Lopez
  - Source: admission_note.pdf, p.1
**Mrn:** SYN-1003
  - Source: admission_note.pdf, p.1

## Admission & discharge dates
**Admission:** 2026-04-02
  - Source: admission_note.pdf, p.1
**Discharge:** 2026-04-06
  - Source: discharge_meds.pdf, p.1

## Diagnoses
**Principal:** Atrial fibrillation with RVR
  - Source: admission_note.pdf, p.1

## Hospital course
**Course:** MISSING — not documented in source notes
  - Flag: MISSING — not documented in source notes

## Procedures
- MISSING — not documented in source notes

## Discharge medications (vs admission)
*Medication reconciliation performed against admission and discharge lists in source notes. FLAGGED: Aspirin: new at discharge without documented reason; Metoprolol: dose changed without documented reason*

- **Aspirin** (new) — not on admission, discharge
- Dose: 81 mg  daily
  - Reason: [NOT DOCUMENTED]
  - Flag: NEW_MED_WITHOUT_DOCUMENTED_REASON
- **Metoprolol** (dose_changed) — admission, discharge
- Dose: 50 mg  twice daily
  - Reason: [NOT DOCUMENTED]
  - Flag: DOSE_CHANGE_WITHOUT_DOCUMENTED_REASON
- **Warfarin** (unchanged) — admission, discharge
- Dose: 5 mg  daily

## Allergies
**Allergy:** NKDA
  - Source: admission_note.pdf, p.1

## Follow-up instructions
**Follow-up:** Cardiology in 2 weeks
  - Source: discharge_meds.pdf, p.1

## Pending results
- NONE — no pending results documented in source notes

## Discharge condition
**Condition:** Rate controlled
  - Source: discharge_meds.pdf, p.1

## Safety escalations
- Increased bleeding risk with warfarin + aspirin combination
- Med reconciliation flag: Aspirin
- Med reconciliation flag: Metoprolol