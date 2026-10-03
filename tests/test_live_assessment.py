import importlib.util
import json
import shutil
import sys
from pathlib import Path

from src.schemas import CriterionAssessment

ROOT = Path(__file__).resolve().parents[1]


def load_script():
    spec = importlib.util.spec_from_file_location("run_live_assessment", ROOT / "scripts" / "run_live_assessment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_reassessment_updates_replay_and_applies_safety(tmp_path, monkeypatch):
    m = load_script()
    saved = tmp_path / "SYN-001_workflow.json"
    shutil.copy(ROOT / "data" / "sample_outputs" / "SYN-001_workflow.json", saved)
    for name, value in {"SAVED_RUN": saved, "BASELINE": tmp_path / "baseline.json",
                        "REPORT_JSON": tmp_path / "report.json", "REPORT_MD": tmp_path / "report.md"}.items():
        monkeypatch.setattr(m, name, value)
    monkeypatch.setattr(m, "_client", lambda: object())

    def fake_assess(criterion, evidence, pages, *, client, model):
        prior = next(e for e in evidence if e.category == "prior_treatment" and "FOLFIRI" in e.value)
        if criterion.type == "exclusion" and "KRAS" in criterion.text.upper():
            # Absence-based clearance: must be downgraded by the safety review.
            return CriterionAssessment(criterion_id=criterion.criterion_id, criterion_text=criterion.text, criterion_type="exclusion",
                                       status="MEETS", method="llm", patient_evidence=[prior], explanation="Only FOLFOX/FOLFIRI listed.")
        return CriterionAssessment(criterion_id=criterion.criterion_id, criterion_text=criterion.text, criterion_type=criterion.type,
                                   status="UNKNOWN", method="llm", patient_evidence=[], explanation="Not documented.")

    monkeypatch.setattr(m, "assess_free_text_criterion", fake_assess)
    monkeypatch.setattr(sys, "argv", ["run_live_assessment.py", "--trials", "NCT06412198"])
    m.main()

    run = json.loads(saved.read_text(encoding="utf-8"))
    items = {a["criterion_id"]: a for a in run["assessments"]["NCT06412198"]}
    assert items["RULE-AGE"]["method"] == "rule"
    assert items["EXC-02"]["status"] == "UNKNOWN"  # absence-based clearance blocked
    assert all(a["method"] == "llm" for k, a in items.items() if not k.startswith("RULE-"))
    assert (tmp_path / "baseline.json").exists() and (tmp_path / "report.md").exists()
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert any("absence-based" in flag for flag in report["trials"]["NCT06412198"]["safety_flags"])
    # Untouched trials keep their baseline assessments.
    assert any(a["method"] == "rule" and not a["criterion_id"].startswith("RULE-") for a in run["assessments"]["NCT06252649"])
