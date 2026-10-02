"""Validate the frozen replay against the guide's working-demo requirements."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.criteria import load_criteria
from src.evidence_view import build_evidence_groups
from src.safety import DISCLAIMER, contains_definitive_eligibility
from src.schemas import CriterionAssessment, EvidenceItem
from src.trial_loader import load_trials


EXPECTED_TRACE = {
    "ingest_documents", "extract_evidence", "verify_quotes", "detect_conflicts",
    "build_patient_query", "retrieve_trials", "rerank_trials",
    "load_trial_criteria", "check_structured_rules", "assess_criteria",
    "safety_review", "prepare_human_review",
}
ALLOWED_LABELS = {
    "Potential match — needs verification",
    "Apparent exclusion — needs verification",
    "Insufficient information",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    replay_path = ROOT / "data" / "sample_outputs" / "SYN-001_workflow.json"
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    evidence = [EvidenceItem.model_validate(item) for item in replay["evidence"]]
    assessments = {
        nct_id: [CriterionAssessment.model_validate(item) for item in items]
        for nct_id, items in replay["assessments"].items()
    }
    trials = load_trials()
    criteria = load_criteria()
    groups = {group.key: group for group in build_evidence_groups(evidence)}

    require(50 <= len(trials) <= 100, "Frozen snapshot must contain 50–100 trials.")
    require(len(criteria) == len(trials), "Every frozen trial needs parsed criteria.")
    require(len(evidence) == 16, "Prepared replay must retain all 16 evidence records.")
    require(all(item.quote_verified for item in evidence), "Every prepared evidence quote must verify.")
    require(groups["ecog"].status == "POTENTIAL_CONFLICT", "ECOG conflict is missing.")
    require(
        {item.value for item in groups["ecog"].items} >= {"ECOG 1", "ECOG 2"},
        "Both ECOG values must remain visible.",
    )
    require(
        groups["prior_kras_g12c_inhibitor"].status == "UNKNOWN",
        "Missing inhibitor history must remain UNKNOWN.",
    )

    candidates = replay["candidate_trials"]
    require(candidates, "Saved replay needs retrieved candidates.")
    require(
        all(item.get("retrieval_mode") == "hybrid_rrf" for item in candidates),
        "Candidates must come from hybrid RRF retrieval.",
    )
    require(
        all("relevance_score" in item and item.get("reason") for item in candidates),
        "Saved candidates need reranker scores and reasons.",
    )
    require(
        all(nct_id in assessments for nct_id in (c["nct_id"] for c in candidates)),
        "Every candidate needs criterion assessments.",
    )
    flat = [item for values in assessments.values() for item in values]
    require(
        any(item.criterion_id == "RULE-AGE" and item.method == "rule" for item in flat),
        "Deterministic age rule is missing.",
    )
    require(
        any(item.criterion_id == "RULE-SEX" and item.method == "rule" for item in flat),
        "Deterministic sex rule is missing.",
    )
    require(any(item.method == "llm" for item in flat), "Saved run needs an LLM criterion assessment.")
    require(any(item.status == "UNKNOWN" for item in flat), "Saved run needs visible unknown criteria.")

    summaries = replay["trial_summaries"]
    require(
        all(value["overall_label"] in ALLOWED_LABELS for value in summaries.values()),
        "Unexpected trial review label.",
    )
    require(
        not any(
            contains_definitive_eligibility(value["overall_label"])
            for value in summaries.values()
        ),
        "Definitive patient eligibility language found.",
    )
    pancreatic = summaries["NCT06782685"]
    require(
        pancreatic["counts"] == {
            "MEETS": 3,
            "DOES_NOT_MEET": 1,
            "UNKNOWN": 26,
            "POTENTIAL_CONFLICT": 0,
        },
        "Pancreatic distractor must retain the diagnosis-mismatch exclusion.",
    )
    require(
        pancreatic["overall_label"] == "Apparent exclusion — needs verification",
        "Pancreatic distractor must require apparent-exclusion review.",
    )
    require(
        replay["human_review"]["candidate_trials"] == candidates,
        "Human-review candidates must match the reranked candidate list.",
    )
    require(
        replay["human_review"]["trial_summaries"] == summaries,
        "Human-review summaries must match the current trial summaries.",
    )
    require(
        any("instruction-like" in flag for flag in replay["safety_flags"]),
        "Prompt-injection defense result is missing.",
    )
    require(
        {item["step"] for item in replay["trace"]} == EXPECTED_TRACE,
        "Saved trace must contain all 12 workflow nodes.",
    )
    require(
        all(item["status"] == "success" for item in replay["trace"]),
        "Every saved trace node must succeed.",
    )
    require(
        "does not determine final clinical-trial eligibility" in DISCLAIMER,
        "Required disclaimer is missing.",
    )

    evaluation = json.loads(
        (ROOT / "data" / "eval" / "evaluation_report.json").read_text(encoding="utf-8")
    )
    require(evaluation["case_count"] >= 10, "Evaluation needs at least 10 cases.")
    require(
        "recall_at_5" in evaluation["retrieval"]["hybrid"],
        "Hybrid Recall@5 is missing.",
    )
    require(
        evaluation["criterion_classification"]["unknown_to_meets_errors"] == 0,
        "Evaluation contains UNKNOWN-to-MEETS errors.",
    )

    print("Demo validation passed")
    print(f"  trials: {len(trials)}")
    print(f"  criteria: {sum(len(items) for items in criteria.values())}")
    print(f"  evidence records: {len(evidence)}")
    print(f"  candidates: {len(candidates)}")
    print(f"  criterion assessments: {len(flat)}")
    print(f"  trace steps: {len(replay['trace'])}")
    print(f"  evaluation cases: {evaluation['case_count']}")


if __name__ == "__main__":
    main()
