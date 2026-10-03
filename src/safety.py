"""Output guardrails for research-trial prescreening."""

from __future__ import annotations

import re

from .schemas import CriterionAssessment


DISCLAIMER = (
    "AI-assisted prescreening only.\n"
    "This system does not determine final clinical-trial eligibility.\n"
    "Research staff must verify source records and trial criteria."
)
INJECTION_PATTERNS = (
    re.compile(r"\bsystem\s+instruction\s*:", re.I),
    re.compile(r"\bignore\s+(?:all\s+)?(?:previous|eligibility|system)\b", re.I),
    re.compile(r"\bmark\s+(?:this\s+)?patient\s+eligible\b", re.I),
)
PROHIBITED_CONCLUSIONS = (
    re.compile(r"\bpatient\s+is\s+eligible\b", re.I),
    re.compile(r"\bpatient\s+qualifies\b", re.I),
    re.compile(r"\benroll\s+(?:this|the)\s+patient\b", re.I),
)


def detect_prompt_injection(text: str) -> list[str]:
    return ["Untrusted source contains instruction-like text; it was treated as data."] if any(pattern.search(text) for pattern in INJECTION_PATTERNS) else []


def contains_definitive_eligibility(text: str) -> bool:
    return any(pattern.search(text) for pattern in PROHIBITED_CONCLUSIONS)


def sanitize_text(text: str) -> str:
    if contains_definitive_eligibility(text):
        return "Unsupported definitive conclusion removed. Human verification is required."
    return text


PRIOR_EXPOSURE = re.compile(r"\b(prior|previous|previously|history of|received|treated with|exposure)\b", re.I)
EXPLICIT_NEGATION = re.compile(r"\b(no prior|no previous|never (?:received|treated)|naive|not previously|none)\b", re.I)


def is_absence_inferred_clearance(item: CriterionAssessment) -> bool:
    """An LLM 'clear of exclusion' for a prior-exposure criterion needs an explicit negative in the record.

    A treatment list (e.g. "FOLFOX, then FOLFIRI") does not show that another therapy was never given.
    """
    if item.method != "llm" or item.criterion_type != "exclusion" or item.status != "MEETS":
        return False
    if not PRIOR_EXPOSURE.search(item.criterion_text):
        return False
    return not any(EXPLICIT_NEGATION.search(e.evidence_text) or EXPLICIT_NEGATION.search(e.value) for e in item.patient_evidence)


def review_assessments(assessments: list[CriterionAssessment]) -> tuple[list[CriterionAssessment], list[str]]:
    """Downgrade unsupported conclusions and return visible review flags."""
    reviewed, flags = [], []
    for item in assessments:
        update = {}
        if item.status in {"MEETS", "DOES_NOT_MEET", "POTENTIAL_CONFLICT"} and not item.patient_evidence and item.method == "llm":
            update = {"status": "UNKNOWN", "explanation": "No patient evidence supports this conclusion; converted to UNKNOWN."}
            flags.append(f"{item.criterion_id}: unsupported conclusion converted to UNKNOWN.")
        elif is_absence_inferred_clearance(item):
            update = {"status": "UNKNOWN", "explanation": "The record does not explicitly rule out this prior exposure; absence from a treatment list is not a negative. Converted to UNKNOWN."}
            flags.append(f"{item.criterion_id}: absence-based clearance of a prior-exposure exclusion converted to UNKNOWN.")
        if any(not evidence.quote_verified for evidence in item.patient_evidence):
            update = {"status": "UNKNOWN", "explanation": "A cited source quote was not verified; converted to UNKNOWN."}
            flags.append(f"{item.criterion_id}: unverified source quote.")
        reviewed.append(item.model_copy(update=update))
    return reviewed, flags
