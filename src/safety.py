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


def review_assessments(assessments: list[CriterionAssessment]) -> tuple[list[CriterionAssessment], list[str]]:
    """Downgrade unsupported conclusions and return visible review flags."""
    reviewed, flags = [], []
    for item in assessments:
        update = {}
        if item.status in {"MEETS", "DOES_NOT_MEET", "POTENTIAL_CONFLICT"} and not item.patient_evidence and item.method == "llm":
            update = {"status": "UNKNOWN", "explanation": "No patient evidence supports this conclusion; converted to UNKNOWN."}
            flags.append(f"{item.criterion_id}: unsupported conclusion converted to UNKNOWN.")
        if any(not evidence.quote_verified for evidence in item.patient_evidence):
            update = {"status": "UNKNOWN", "explanation": "A cited source quote was not verified; converted to UNKNOWN."}
            flags.append(f"{item.criterion_id}: unverified source quote.")
        reviewed.append(item.model_copy(update=update))
    return reviewed, flags
