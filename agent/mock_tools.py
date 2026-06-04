"""Mock external tools — agent decides when to invoke; deterministic safety responses."""



from __future__ import annotations



from typing import Any





# Deterministic known interaction pairs (no random generation)

KNOWN_INTERACTIONS: dict[frozenset[str], dict[str, str]] = {

    frozenset({"warfarin", "aspirin"}): {

        "severity": "HIGH",

        "message": "Increased bleeding risk with warfarin + aspirin combination",

    },

    frozenset({"lisinopril", "spironolactone"}): {

        "severity": "MEDIUM",

        "message": "ACE inhibitor with spironolactone increases hyperkalemia risk",

    },

    frozenset({"lisinopril", "potassium"}): {

        "severity": "MEDIUM",

        "message": "ACE inhibitor with potassium supplementation may cause hyperkalemia",

    },

    frozenset({"metformin", "contrast"}): {

        "severity": "MEDIUM",

        "message": "Metformin held around iodinated contrast per protocol — verify resume timing",

    },

}





def lookup_drug_interactions(medications: list[str]) -> dict[str, Any]:

    """

    Mock drug–drug interaction lookup using KNOWN_INTERACTIONS only.

    Returns interactions found; empty if none.

    """

    if not medications:

        return {"ok": True, "interactions": [], "message": "No medications provided"}



    norms = [m.lower().strip() for m in medications]

    found: list[dict[str, str]] = []

    seen_messages: set[str] = set()



    def _add(pair: list[str], info: dict[str, str]) -> None:

        if info["message"] in seen_messages:

            return

        seen_messages.add(info["message"])

        found.append(

            {

                "pair": pair,

                "severity": info["severity"],

                "message": info["message"],

                "source": "KNOWN_INTERACTIONS",

            }

        )



    for i, a in enumerate(norms):

        for b in norms[i + 1 :]:

            key = frozenset({_drug_token(a), _drug_token(b)})

            if key in KNOWN_INTERACTIONS:

                _add([a, b], KNOWN_INTERACTIONS[key])



    return {

        "ok": True,

        "interactions": found,

        "checked_count": len(norms),

        "tool": "drug_interaction_lookup",

    }





def escalate_safety_concern(

    concern_type: str,

    message: str,

    severity: str = "high",

    patient_id: str | None = None,

) -> dict[str, Any]:

    """Mock escalation / flag for pharmacist or attending review."""

    return {

        "ok": True,

        "escalated": True,

        "ticket_id": f"ESC-{patient_id or 'UNK'}-{concern_type[:8].upper()}",

        "severity": severity,

        "message": message,

        "tool": "safety_escalation",

        "status": "QUEUED_FOR_REVIEW",

    }





def _drug_token(med: str) -> str:

    return med.split()[0].lower() if med else ""

