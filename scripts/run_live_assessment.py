"""Re-assess the saved SYN-001 run's free-text criteria with the live LLM assessor.

Usage (from the repository root, with OPENAI_API_KEY in .env or the environment):

    python scripts/run_live_assessment.py --dry-run          # show what would run
    python scripts/run_live_assessment.py                    # top 3 reranked trials
    python scripts/run_live_assessment.py --trials NCT06412198 NCT06252649

What it does:
  * keeps the deterministic age/sex rule results unchanged;
  * sends every free-text criterion of the chosen trials to the LLM assessor
    (one bounded source-page tool available), falling back to the conservative
    rule baseline if a call fails;
  * applies the same safety review as the workflow (unsupported or
    unverified conclusions and absence-based clearances become UNKNOWN);
  * saves the original run once as SYN-001_workflow_baseline.json, writes the
    updated replay, and writes a review report listing every change a clinician
    should check before the replay is used in a demo.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values  # noqa: E402
from openai import OpenAI  # noqa: E402

from src.eligibility import assess_free_text_criterion, conservative_assessment, summarize_trial  # noqa: E402
from src.safety import review_assessments  # noqa: E402
from src.schemas import CriterionAssessment, DocumentPage, EvidenceItem, TrialCriterion  # noqa: E402

OUTPUT_DIR = ROOT / "data" / "sample_outputs"
SAVED_RUN = OUTPUT_DIR / "SYN-001_workflow.json"
BASELINE = OUTPUT_DIR / "SYN-001_workflow_baseline.json"
REPORT_JSON = OUTPUT_DIR / "SYN-001_live_assessment_report.json"
REPORT_MD = OUTPUT_DIR / "SYN-001_live_assessment_report.md"
DEFAULT_MODEL = "gpt-4.1-mini"


def _client() -> OpenAI:
    settings = dotenv_values(ROOT / ".env", encoding="utf-8-sig")
    key = (os.environ.get("OPENAI_API_KEY") or settings.get("OPENAI_API_KEY") or "").strip()
    if not key or key == "your_api_key_here":
        raise SystemExit("Set OPENAI_API_KEY in the repository .env file or the environment.")
    return OpenAI(api_key=key, timeout=60.0, max_retries=2)


def _needs_clinical_review(before: dict, after: CriterionAssessment) -> list[str]:
    reasons = []
    if before["status"] == "UNKNOWN" and after.status in {"MEETS", "DOES_NOT_MEET"}:
        reasons.append(f"resolved from UNKNOWN to {after.status}")
    if after.criterion_type == "exclusion" and after.status == "MEETS":
        reasons.append("exclusion marked clear (MEETS); confirm the record explicitly rules it out")
    if after.status == "DOES_NOT_MEET":
        reasons.append("criterion appears not met / exclusion appears to apply")
    if before["status"] != after.status and before["status"] != "UNKNOWN":
        reasons.append(f"changed from {before['status']} to {after.status}")
    return reasons


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trials", nargs="*", help="NCT IDs to re-assess (default: top 3 reranked candidates)")
    parser.add_argument("--model", default=os.environ.get("OPENAI_ASSESSMENT_MODEL", DEFAULT_MODEL))
    parser.add_argument("--dry-run", action="store_true", help="list the criteria that would be sent; make no API calls")
    args = parser.parse_args()

    source = BASELINE if BASELINE.exists() else SAVED_RUN
    run = json.loads(source.read_text(encoding="utf-8"))
    pages = [DocumentPage.model_validate(p) for p in run["pages"]]
    evidence = [EvidenceItem.model_validate(e) for e in run["evidence"]]
    trials = args.trials or [c["nct_id"] for c in run["candidate_trials"][:3]]
    unknown = [t for t in trials if t not in run["trial_criteria"]]
    if unknown:
        raise SystemExit(f"Not in the saved run: {', '.join(unknown)}")
    planned = {t: [TrialCriterion.model_validate(c) for c in run["trial_criteria"][t]] for t in trials}
    total = sum(len(v) for v in planned.values())
    print(f"Source run: {source.name}")
    print(f"Trials: {', '.join(trials)}  |  free-text criteria to assess: {total}  |  model: {args.model}")
    if args.dry_run:
        for t, items in planned.items():
            print(f"  {t}: {len(items)} criteria")
        return

    if not BASELINE.exists():
        BASELINE.write_text(SAVED_RUN.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Saved the original run as {BASELINE.name}")

    client = _client()
    started = perf_counter()
    llm_calls = errors = 0
    report = {"model": args.model, "source_run": source.name, "trials": {}, "needs_clinical_review": [], "errors": []}
    for nct_id, criteria in planned.items():
        before = {a["criterion_id"]: a for a in run["assessments"][nct_id]}
        rules = [CriterionAssessment.model_validate(a) for a in run["assessments"][nct_id] if a["criterion_id"].startswith("RULE-")]
        assessed = []
        for index, criterion in enumerate(criteria, start=1):
            try:
                result = assess_free_text_criterion(criterion, evidence, pages, client=client, model=args.model)
                llm_calls += 1
            except Exception as exc:  # keep going; the baseline is the safe fallback
                errors += 1
                report["errors"].append({"trial": nct_id, "criterion_id": criterion.criterion_id, "error": f"{type(exc).__name__}: {exc}"})
                result = conservative_assessment(criterion, evidence)
            assessed.append(result)
            print(f"  {nct_id} {index}/{len(criteria)} {criterion.criterion_id}: {result.status} ({result.method})")
        reviewed, flags = review_assessments(rules + assessed)
        run["assessments"][nct_id] = [a.model_dump(mode="json") for a in reviewed]
        run["trial_summaries"][nct_id] = summarize_trial(reviewed)
        run["safety_flags"] = sorted(set(run.get("safety_flags", [])) | set(flags))
        transitions = Counter(f"{before.get(a.criterion_id, {}).get('status', 'NEW')} -> {a.status}" for a in reviewed)
        report["trials"][nct_id] = {
            "before": next((s for t, s in json.loads(source.read_text(encoding='utf-8'))["trial_summaries"].items() if t == nct_id), {}),
            "after": run["trial_summaries"][nct_id],
            "methods": dict(Counter(a.method for a in reviewed)),
            "transitions": dict(transitions),
            "safety_flags": flags,
        }
        for item in reviewed:
            reasons = _needs_clinical_review(before.get(item.criterion_id, {"status": "UNKNOWN"}), item)
            if reasons and not item.criterion_id.startswith("RULE-"):
                report["needs_clinical_review"].append({
                    "trial": nct_id, "criterion_id": item.criterion_id, "type": item.criterion_type,
                    "criterion": item.criterion_text, "status": item.status, "method": item.method,
                    "reasons": reasons, "explanation": item.explanation,
                    "evidence": [f"{e.source_file} p{e.source_page}: {e.evidence_text}" for e in item.patient_evidence],
                })

    for step in run.get("trace", []):
        if step.get("step") == "assess_criteria":
            step.update({"llm_calls": llm_calls + 1, "model": args.model,
                         "latency_ms": round((perf_counter() - started) * 1000, 2),
                         "note": f"Live LLM re-assessment of {', '.join(trials)}; other trials use the rule baseline."})
    run["human_review"]["trial_summaries"] = run["trial_summaries"]
    SAVED_RUN.write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = ["# Live LLM assessment report", "", f"Model: `{args.model}` · trials: {', '.join(trials)} · LLM calls: {llm_calls} · errors: {errors}", ""]
    lines += ["| Trial | Before (M/DNM/U/PC) | After (M/DNM/U/PC) | Label after |", "|---|---|---|---|"]
    for nct_id, info in report["trials"].items():
        fmt = lambda s: "/".join(str(s.get("counts", {}).get(k, 0)) for k in ("MEETS", "DOES_NOT_MEET", "UNKNOWN", "POTENTIAL_CONFLICT"))
        lines.append(f"| {nct_id} | {fmt(info['before'])} | {fmt(info['after'])} | {info['after'].get('overall_label', '')} |")
    lines += ["", f"## Needs clinical review ({len(report['needs_clinical_review'])})", "",
              "Check each item against the evidence before using this replay in a demo or post.", ""]
    for item in report["needs_clinical_review"]:
        lines += [f"### {item['trial']} {item['criterion_id']} ({item['type']}) — {item['status']}",
                  f"- Criterion: {item['criterion']}", f"- Why flagged: {'; '.join(item['reasons'])}",
                  f"- Explanation: {item['explanation']}"]
        lines += [f"- Evidence: {e}" for e in item["evidence"]] or ["- Evidence: none cited"]
        lines.append("")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nDone: {llm_calls} LLM assessments, {errors} errors, {len(report['needs_clinical_review'])} items flagged for clinical review.")
    print(f"Updated {SAVED_RUN.name}; report in {REPORT_MD.name}")


if __name__ == "__main__":
    main()
