from src.eligibility import assess_age_rule, assess_sex_rule, conservative_assessment, summarize_trial
from src.schemas import EvidenceItem, TrialCriterion
from src.trial_loader import load_trials, parse_age_to_years


def evidence(category, value, *, date=None):
    return EvidenceItem(category=category, value=value, date=date, source_file="case.txt", source_page=1, evidence_text=value, quote_verified=True)


def test_age_parser_and_missing_age_rule():
    assert parse_age_to_years("18 Years") == 18
    trial = load_trials()[0]
    assert assess_age_rule(trial, []).status == "UNKNOWN"


def test_age_and_sex_rules_use_structured_fields():
    trial = load_trials()[0]
    assert assess_age_rule(trial, [evidence("age", "58 years")]).status == "MEETS"
    assert assess_sex_rule(trial, [evidence("sex", "Female")]).status == "MEETS"


def test_exclusion_direction_when_exclusion_applies():
    criterion = TrialCriterion(criterion_id="EXC-01", type="exclusion", text="Exclude KRAS G12C mutation")
    item = evidence("biomarker", "KRAS G12C mutation detected")
    assessment = conservative_assessment(criterion, [item])
    assert assessment.status == "DOES_NOT_MEET"
    assert summarize_trial([assessment])["overall_label"].startswith("Apparent exclusion")


def test_differing_ecog_values_can_remain_conflict():
    criterion = TrialCriterion(criterion_id="INC-01", type="inclusion", text="ECOG 0-1")
    items = [evidence("performance_status", "ECOG 1", date="2026-01-01"), evidence("performance_status", "ECOG 2", date="2026-02-01")]
    result = conservative_assessment(criterion, items)
    assert result.status == "POTENTIAL_CONFLICT"
    assert {x.date for x in result.patient_evidence} == {"2026-01-01", "2026-02-01"}


def test_different_primary_cancer_is_does_not_meet():
    criterion = TrialCriterion(criterion_id="INC-02", type="inclusion", text="Patients with pancreatic cancer diagnosed by histopathology or cytology;")
    item = evidence("diagnosis", "Metastatic colorectal adenocarcinoma")
    result = conservative_assessment(criterion, [item])
    assert result.status == "DOES_NOT_MEET"
    assert summarize_trial([result])["overall_label"].startswith("Apparent exclusion")


def test_metastatic_site_wording_is_not_a_diagnosis_mismatch():
    criterion = TrialCriterion(criterion_id="INC-03", type="inclusion", text="Measurable disease, including lung metastases from colorectal cancer")
    item = evidence("diagnosis", "Metastatic colorectal adenocarcinoma")
    assert conservative_assessment(criterion, [item]).status != "DOES_NOT_MEET"


def test_matching_or_multi_site_criterion_is_not_a_mismatch():
    criterion = TrialCriterion(criterion_id="INC-04", type="inclusion", text="Histologically confirmed NSCLC, colorectal or pancreatic cancer")
    item = evidence("diagnosis", "Metastatic colorectal adenocarcinoma")
    assert conservative_assessment(criterion, [item]).status != "DOES_NOT_MEET"
