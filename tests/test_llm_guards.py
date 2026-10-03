"""Guards built from the first live LLM run on SYN-001 (data/sample_outputs/SYN-001_live_assessment_report.md)."""

import pytest

from src.safety import review_assessments
from src.schemas import CriterionAssessment, EvidenceItem


def ev(category, text):
    return EvidenceItem(category=category, value=text, source_file="note.pdf", source_page=1, evidence_text=text, quote_verified=True)


AGE, SEX = ev("age", "Age: 58 years"), ev("sex", "Sex: Female")
DIAG, LIVER = ev("diagnosis", "Diagnosis: Metastatic colorectal adenocarcinoma"), ev("metastatic_site", "Metastatic site: Liver")
ANC, HB = ev("lab", "Absolute neutrophil count (ANC): 2.1 x 10^9/L"), ev("lab", "Hemoglobin: 11.2 g/dL")
KRAS, MSS = ev("biomarker", "KRAS: G12C mutation detected"), ev("biomarker", "MSI: microsatellite stable (MSS)")
TX = ev("prior_treatment", "Prior treatment: FOLFOX, then FOLFIRI")


def llm(cid, text, status, evidence, kind="inclusion"):
    return CriterionAssessment(criterion_id=cid, criterion_text=text, criterion_type=kind, status=status, method="llm", patient_evidence=evidence, explanation="model reasoning")


CASES = [
    # Correct resolutions that must survive the guards.
    (llm("INC-03", "Unresectable or metastatic disease.", "MEETS", [DIAG, LIVER]), "MEETS"),
    (llm("INC-07", "Age ≥ 18 years.", "MEETS", [AGE]), "MEETS"),
    (llm("INC-13", "Absolute neutrophil count ≥ 1,000/mm3 (≥ 1.0 x 109/L)", "MEETS", [ANC]), "MEETS"),
    (llm("INC-01b", "Male or female, aged 18-75 years.", "MEETS", [AGE, SEX]), "MEETS"),
    # Unsafe clearances from the first run.
    (llm("INC-15", "Hemoglobin ≥ 9 g/dL, in the absence of transfusions for at least 2 weeks", "MEETS", [HB]), "UNKNOWN"),
    (llm("INC-02", "Central laboratory detection of KRAS p.G12C mutation.", "MEETS", [KRAS]), "UNKNOWN"),
    (llm("INC-03b", "Unresectable, MSS-type metastatic colorectal cancer that has failed or is intolerant to first-line standard oxaliplatin plus fluoropyrimidine ± targeted therapy.", "MEETS", [TX, MSS]), "UNKNOWN"),
    (llm("INC-10", "Hematology: Hb ≥ 90 g/L; WBC ≥ 3.0 × 10⁹/L; ANC ≥ 1.5 × 10⁹/L; PLT ≥ 90 × 10⁹/L.", "MEETS", [ANC, HB]), "UNKNOWN"),
    # Option and conditional sub-items wrongly read as requirements.
    (llm("INC-25", "Male sterilization with confirmed absence of sperm in the post-vasectomy ejaculate.", "DOES_NOT_MEET", [SEX]), "UNKNOWN"),
    (llm("INC-14", "No liver mets: TBIL ≤ 1.5 × ULN, ALT ≤ 2.5 × ULN, AST ≤ 2.5 × ULN.", "DOES_NOT_MEET", [LIVER]), "UNKNOWN"),
]


@pytest.mark.parametrize("assessment,expected", CASES, ids=[c[0].criterion_id for c in CASES])
def test_first_live_run_items(assessment, expected):
    reviewed, flags = review_assessments([assessment])
    assert reviewed[0].status == expected
    if expected != assessment.status:
        assert flags and "Original reasoning" in reviewed[0].explanation


def test_rule_assessments_are_not_touched_by_llm_guards():
    rule = CriterionAssessment(criterion_id="INC-10", criterion_text="Hb ≥ 90 g/L; WBC ≥ 3.0", criterion_type="inclusion", status="MEETS", method="rule", patient_evidence=[HB], explanation="rule")
    assert review_assessments([rule])[0][0].status == "MEETS"


def test_true_exclusion_from_documented_fact_is_kept():
    item = llm("INC-02", "Patients with pancreatic cancer diagnosed by histopathology", "DOES_NOT_MEET", [DIAG])
    assert review_assessments([item])[0][0].status == "DOES_NOT_MEET"


def test_investigator_judgment_criterion_cannot_be_cleared():
    item = llm("EXC-21", "Any serious illness ... which, in the investigator's opinion, would be likely to interfere with the participant's participation in the study.", "MEETS", [TX], kind="exclusion")
    reviewed, flags = review_assessments([item])
    assert reviewed[0].status == "UNKNOWN" and any("investigator-judgment" in f for f in flags)


def test_exclusion_answers_are_mapped_by_code_not_by_the_model():
    from src.eligibility import _project_status
    assert _project_status("exclusion", "APPLIES") == "DOES_NOT_MEET"
    assert _project_status("exclusion", "does_not_apply") == "MEETS"
    assert _project_status("exclusion", "DOES_NOT_MEET") is None  # wrong vocabulary is rejected, never guessed
    assert _project_status("inclusion", "MEETS") == "MEETS"
    assert _project_status("inclusion", "APPLIES") is None


def test_exclusion_answer_from_model_flows_through_assessor():
    from types import SimpleNamespace
    from src.eligibility import assess_free_text_criterion, _LLMAssessment
    from src.schemas import TrialCriterion

    class FakeResponses:
        def parse(self, **kwargs):
            return SimpleNamespace(id="r", output=[], output_parsed=_LLMAssessment(status="APPLIES", evidence_indices=[0], explanation="Exclusion applies."))

    criterion = TrialCriterion(criterion_id="EXC-09", type="exclusion", text="Patients with pancreatic cancer")
    result = assess_free_text_criterion(criterion, [DIAG], [], client=SimpleNamespace(responses=FakeResponses()))
    assert result.status == "DOES_NOT_MEET" and result.method == "llm"


ECOG1, ECOG2 = ev("performance_status", "Performance status: ECOG 1"), ev("performance_status", "ECOG 2")
BRAF = ev("biomarker", "BRAF: wild type")


@pytest.mark.parametrize("text,evidence,expected", [
    # Second live run: catch-all exclusion cleared from silence.
    ("Other severe uncontrolled disorders (e.g., frequent seizures, hepatic failure).", [ECOG1, ECOG2], "UNKNOWN"),
    ("Any illness or medical history that would impact safety or compliance with study requirements", [ECOG1], "UNKNOWN"),
    ("Active brain metastases, unless adequately treated", [LIVER], "UNKNOWN"),
    # Clearance by a documented fact about the same thing is kept.
    ("Patients whose cancers possess BRAF V600 mutations are excluded.", [BRAF], "MEETS"),
    ("Patients must not have mismatch repair deficient or microsatellite instability high cancers.", [MSS], "MEETS"),
    ("Patients aged under 18 years", [AGE], "MEETS"),
])
def test_exclusion_clearance_needs_evidence_about_the_exclusion(text, evidence, expected):
    reviewed, _ = review_assessments([llm("EXC-X", text, "MEETS", evidence, kind="exclusion")])
    assert reviewed[0].status == expected


# From the held-out run (data/eval/criterion_eval_report_heldout.md): MEETS on "adequate hematological,
# renal, and hepatic function" with no liver tests cited. Guard added after that run.
CREAT = ev("lab", "Creatinine: 0.9 mg/dL")
PLT, BILI = ev("lab", "Platelets: 210 x 10^9/L"), ev("lab", "Total bilirubin: 0.6 mg/dL")
ALT, AST = ev("lab", "ALT: 22 U/L"), ev("lab", "AST: 25 U/L")
ORGAN_CASES = [
    (llm("INC-04", "Adequate hematological, renal, and hepatic function", "MEETS", [ANC, HB, CREAT]), "UNKNOWN"),
    (llm("INC-04b", "Adequate hematological, renal, and hepatic function", "MEETS", [ANC, HB, PLT, CREAT, BILI, ALT, AST]), "MEETS"),
    (llm("INC-05", "Adequate renal function", "MEETS", [CREAT]), "MEETS"),
    (llm("INC-06", "Adequate organ function", "MEETS", [ANC, HB, CREAT]), "UNKNOWN"),
    # Not an organ-function criterion: hepatic metastases wording must not trigger the guard.
    (llm("INC-07", "Metastatic colorectal cancer, including hepatic metastases", "MEETS", [DIAG, LIVER]), "MEETS"),
]


@pytest.mark.parametrize("assessment,expected", ORGAN_CASES, ids=[c[0].criterion_id for c in ORGAN_CASES])
def test_organ_function_needs_every_named_system(assessment, expected):
    reviewed, _ = review_assessments([assessment])
    assert reviewed[0].status == expected


# From the live run after the held-out fixes: "FOLFOX, then FOLFIRI" read as FOLFIRI in first line,
# which wrongly made NCT07559760 an apparent exclusion.
FIRST_LINE = ev("prior_treatment", "First-line: FOLFOX; second-line: FOLFIRI")
TOPO = "Prior exposure to topoisomerase-I inhibitors or their analogues in first-line therapy."
LINE_CASES = [
    (llm("EXC-01", TOPO, "DOES_NOT_MEET", [TX], kind="exclusion"), "UNKNOWN"),
    (llm("EXC-01b", TOPO, "MEETS", [TX], kind="exclusion"), "UNKNOWN"),
    (llm("INC-05", "Adjuvant setting: recurrence within 6 months of adjuvant oxaliplatin", "MEETS", [TX]), "UNKNOWN"),
]


@pytest.mark.parametrize("assessment,expected", LINE_CASES, ids=[c[0].criterion_id for c in LINE_CASES])
def test_line_of_therapy_must_be_stated(assessment, expected):
    reviewed, _ = review_assessments([assessment])
    assert reviewed[0].status == expected


def test_line_guard_accepts_stated_lines():
    from src.safety import is_unstated_line_of_therapy
    assert not is_unstated_line_of_therapy(llm("EXC-01c", TOPO, "DOES_NOT_MEET", [FIRST_LINE], kind="exclusion"))
