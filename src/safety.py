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


# Requirements a cited fact must actually mention before an LLM MEETS is accepted.
UNSUPPORTED_QUALIFIERS = re.compile(
    r"\b(central|failed|failure|intoleran\w*|progress\w*|refractory|transfus\w*|clearance|"
    r"measurable|recist|confirmed absence)\b",
    re.I,
)
LAB_ANALYTES = {
    "hemoglobin": re.compile(r"\b(hb|hgb|hemoglobin|haemoglobin)\b", re.I),
    "white blood cells": re.compile(r"\b(wbc|white blood cells?|leukocytes?)\b", re.I),
    "neutrophils": re.compile(r"\b(anc|neutrophils?)\b", re.I),
    "platelets": re.compile(r"\b(plt|platelets?)\b", re.I),
    "bilirubin": re.compile(r"\b(tbil|bilirubin)\b", re.I),
    "ALT": re.compile(r"\balt\b", re.I),
    "AST": re.compile(r"\bast\b", re.I),
    "INR": re.compile(r"\binr\b", re.I),
    "creatinine": re.compile(r"\bcreatinine\b", re.I),
}
# "Adequate hematologic, renal and hepatic function" is met only when every named organ system has
# its usual results cited. Applies only when the criterion is about organ *function*, so mentions
# such as "hepatic metastases" are unaffected. "Adequate organ function" names all three systems.
FUNCTION_WORDING = re.compile(r"\bfunctions?\b", re.I)
ORGAN_FUNCTION = {
    "hematologic function": (re.compile(r"\b(ha?ematolog\w*|bone marrow|organ)\b", re.I), ("neutrophils", "hemoglobin", "platelets")),
    "renal function": (re.compile(r"\b(renal|kidney|organ)\b", re.I), ("creatinine",)),
    "hepatic function": (re.compile(r"\b(hepatic|liver|organ)\b", re.I), ("bilirubin", "ALT", "AST")),
}
# Fragments that are one option in a list, or a branch that applies only under a condition.
CONDITIONAL_OR_OPTION = re.compile(
    r"^\s*(?:if\b|for (?:participants|patients|subjects)\b|note\b|no [\w\s-]{1,30}:|[\w\s-]{1,30} mets?:)"
    r"|contracepti|sterili[sz]|vasectomy|condom|intrauterine|\biud\b|tubal|salpingectomy|post-menopausal|hormonal methods",
    re.I,
)


# Criteria only an investigator can judge; records cannot settle them in prescreening.
INVESTIGATOR_JUDGMENT = re.compile(
    r"investigator'?s?\s+(?:opinion|judg(?:e)?ment|discretion)|in the opinion of|deemed by the investigator|"
    r"deemed (?:unsuitable|inappropriate)|unsuitable for enrol",
    re.I,
)


# Words too generic to show that cited evidence is about the same thing as an exclusion.
GENERIC_TERMS = frozenset("""
a an and any are as at be by for from has have history in including is known of on or other patient patients
prior previous current currently within month months year years week weeks day days disease diseases disorder
disorders condition conditions cancer cancers tumor tumors tumour malignancy malignancies therapy therapies
treatment treatments treated status severe uncontrolled active such that the this those to with would must not
no clinically significant e g eg study participant participants subject subjects metastases metastasis
metastatic require required requiring use using evidence documented
""".split())


def _terms(text: str) -> set[str]:
    terms = set()
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        word = word.rstrip("s")
        if word.endswith("ed") and len(word) >= 4:  # aged -> age, mutated -> mutate
            word = word[:-1]
        if len(word) >= 3 and word not in GENERIC_TERMS:
            terms.add(word)
    return terms


def is_unsupported_exclusion_clearance(item: CriterionAssessment) -> bool:
    """An LLM 'clear of exclusion' must rest on evidence about the excluded condition, not on silence.

    Accepted when the cited evidence explicitly negates (e.g. "no prior ...") or shares a specific
    term with the criterion (e.g. BRAF wild type for a BRAF V600 exclusion). ECOG 1 does not clear
    "frequent seizures, hepatic failure".
    """
    if item.method != "llm" or item.criterion_type != "exclusion" or item.status != "MEETS":
        return False
    if any(EXPLICIT_NEGATION.search(e.evidence_text) or EXPLICIT_NEGATION.search(e.value) for e in item.patient_evidence):
        return False
    criterion_terms = _terms(item.criterion_text)
    cited_terms = set().union(*(_terms(f"{e.value} {e.evidence_text}") for e in item.patient_evidence)) if item.patient_evidence else set()
    return not (criterion_terms & cited_terms)


def _cited_text(item: CriterionAssessment) -> str:
    return " ".join(f"{e.value} {e.evidence_text}" for e in item.patient_evidence)


def uncovered_requirements(item: CriterionAssessment) -> list[str]:
    """Requirements of an LLM 'MEETS' inclusion that the cited evidence does not mention."""
    if item.method != "llm" or item.criterion_type != "inclusion" or item.status != "MEETS":
        return []
    cited = _cited_text(item)
    missing = sorted({m.group(0).lower() for m in UNSUPPORTED_QUALIFIERS.finditer(item.criterion_text)
                      if not re.search(re.escape(m.group(0)), cited, re.I)})
    missing += [name for name, pattern in LAB_ANALYTES.items()
                if pattern.search(item.criterion_text) and not pattern.search(cited)]
    for system, (mention, analytes) in ORGAN_FUNCTION.items():
        if FUNCTION_WORDING.search(item.criterion_text) and mention.search(item.criterion_text):
            absent = [a for a in analytes if not LAB_ANALYTES[a].search(cited)]
            if absent:
                missing.append(f"{system}: {', '.join(absent)}")
    return missing


def is_conditional_or_option_rejection(item: CriterionAssessment) -> bool:
    """An LLM 'DOES_NOT_MEET' on a list option or conditional branch is not evidence of exclusion."""
    return (item.method == "llm" and item.criterion_type == "inclusion" and item.status == "DOES_NOT_MEET"
            and bool(CONDITIONAL_OR_OPTION.search(item.criterion_text)))


def review_assessments(assessments: list[CriterionAssessment]) -> tuple[list[CriterionAssessment], list[str]]:
    """Downgrade unsupported conclusions and return visible review flags."""
    reviewed, flags = [], []
    for item in assessments:
        update = {}
        if item.status in {"MEETS", "DOES_NOT_MEET", "POTENTIAL_CONFLICT"} and INVESTIGATOR_JUDGMENT.search(item.criterion_text):
            update = {"status": "UNKNOWN", "explanation": f"This criterion depends on investigator judgment and cannot be settled from records; converted to UNKNOWN. Original reasoning: {item.explanation}"}
            flags.append(f"{item.criterion_id}: investigator-judgment criterion converted to UNKNOWN.")
        elif item.status in {"MEETS", "DOES_NOT_MEET", "POTENTIAL_CONFLICT"} and not item.patient_evidence and item.method == "llm":
            update = {"status": "UNKNOWN", "explanation": "No patient evidence supports this conclusion; converted to UNKNOWN."}
            flags.append(f"{item.criterion_id}: unsupported conclusion converted to UNKNOWN.")
        elif is_absence_inferred_clearance(item):
            update = {"status": "UNKNOWN", "explanation": "The record does not explicitly rule out this prior exposure; absence from a treatment list is not a negative. Converted to UNKNOWN."}
            flags.append(f"{item.criterion_id}: absence-based clearance of a prior-exposure exclusion converted to UNKNOWN.")
        elif is_unsupported_exclusion_clearance(item):
            update = {"status": "UNKNOWN", "explanation": f"No cited evidence addresses this exclusion; absence of a record does not clear it. Converted to UNKNOWN. Original reasoning: {item.explanation}"}
            flags.append(f"{item.criterion_id}: exclusion cleared without evidence about it; converted to UNKNOWN.")
        elif missing := uncovered_requirements(item):
            update = {"status": "UNKNOWN", "explanation": f"Part of this criterion is not documented ({', '.join(missing)}); converted to UNKNOWN. Original reasoning: {item.explanation}"}
            flags.append(f"{item.criterion_id}: partial evidence ({', '.join(missing)} not documented); converted to UNKNOWN.")
        elif is_conditional_or_option_rejection(item):
            update = {"status": "UNKNOWN", "explanation": f"This item is a conditional branch or one option among alternatives, so not meeting it does not show exclusion; reviewer decides applicability. Original reasoning: {item.explanation}"}
            flags.append(f"{item.criterion_id}: conditional or option sub-item; DOES_NOT_MEET converted to UNKNOWN.")
        if any(not evidence.quote_verified for evidence in item.patient_evidence):
            update = {"status": "UNKNOWN", "explanation": "A cited source quote was not verified; converted to UNKNOWN."}
            flags.append(f"{item.criterion_id}: unverified source quote.")
        reviewed.append(item.model_copy(update=update))
    return reviewed, flags
