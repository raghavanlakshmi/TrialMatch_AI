"""Score criterion-level prescreening against labeled SYN-001 criteria.

    python scripts/run_criterion_eval.py            # rule baseline only (no API calls)
    python scripts/run_criterion_eval.py --llm      # also the live LLM assessor (needs OPENAI_API_KEY)

Labels live in data/eval/criterion_labels.json. Both methods are scored after the
same safety review the workflow applies. Metrics:

  * accuracy                      share of labels matched exactly
  * decided-correctly             of labels whose answer is decidable (not UNKNOWN), share matched
  * unsafe false clearance        predicted MEETS where the label is anything else
  * false exclusion               predicted DOES_NOT_MEET where the label is UNKNOWN or MEETS
  * unknown_to_meets              predicted MEETS where the label is UNKNOWN (the most dangerous error)
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.criteria import load_criteria  # noqa: E402
from src.eligibility import conservative_assessment  # noqa: E402
from src.safety import review_assessments  # noqa: E402
from src.schemas import DocumentPage, EvidenceItem  # noqa: E402

LABELS = ROOT / "data" / "eval" / "criterion_labels.json"
SAVED_RUN = ROOT / "data" / "sample_outputs" / "SYN-001_workflow.json"
BASELINE_RUN = ROOT / "data" / "sample_outputs" / "SYN-001_workflow_baseline.json"
REPORT_JSON = ROOT / "data" / "eval" / "criterion_eval_report.json"
REPORT_MD = ROOT / "data" / "eval" / "criterion_eval_report.md"
STATUSES = ("MEETS", "DOES_NOT_MEET", "UNKNOWN", "POTENTIAL_CONFLICT")


def score(pairs: list[tuple[str, str]]) -> dict:
    total = len(pairs)
    decidable = [(e, p) for e, p in pairs if e != "UNKNOWN"]
    confusion = {e: {p: 0 for p in STATUSES} for e in STATUSES}
    for expected, predicted in pairs:
        confusion[expected][predicted] += 1
    return {
        "labels": total,
        "accuracy": round(sum(e == p for e, p in pairs) / total, 4) if total else None,
        "decidable_labels": len(decidable),
        "decided_correctly": round(sum(e == p for e, p in decidable) / len(decidable), 4) if decidable else None,
        "unsafe_false_clearance": sum(p == "MEETS" and e != "MEETS" for e, p in pairs),
        "false_exclusion": sum(p == "DOES_NOT_MEET" and e in {"UNKNOWN", "MEETS"} for e, p in pairs),
        "unknown_to_meets": sum(e == "UNKNOWN" and p == "MEETS" for e, p in pairs),
        "confusion_matrix": confusion,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--llm", action="store_true", help="also score the live LLM assessor")
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--labels", type=Path, default=LABELS, help="label file (default: criterion_labels.json)")
    args = parser.parse_args()
    suffix = "" if args.labels == LABELS else "_" + args.labels.stem.replace("criterion_labels_", "")
    report_json = REPORT_JSON.with_name(f"criterion_eval_report{suffix}.json")
    report_md = REPORT_MD.with_name(f"criterion_eval_report{suffix}.md")

    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    run = json.loads((BASELINE_RUN if BASELINE_RUN.exists() else SAVED_RUN).read_text(encoding="utf-8"))
    evidence = [EvidenceItem.model_validate(e) for e in run["evidence"]]
    pages = [DocumentPage.model_validate(p) for p in run["pages"]]
    criteria = load_criteria()

    methods = {"rule_baseline": lambda c: conservative_assessment(c, evidence)}
    if args.llm:
        sys.path.insert(0, str(ROOT / "scripts"))
        from run_live_assessment import _client  # noqa: E402
        from src.eligibility import assess_free_text_criterion  # noqa: E402

        client = _client()
        methods["llm_assessor"] = lambda c: assess_free_text_criterion(c, evidence, pages, client=client, model=args.model)

    rows, results = [], {}
    for name, assess in methods.items():
        pairs = []
        for label in labels["labels"]:
            criterion = next(c for c in criteria[label["trial"]] if c.criterion_id == label["criterion_id"])
            reviewed, flags = review_assessments([assess(criterion)])
            predicted = reviewed[0].status
            pairs.append((label["expected"], predicted))
            rows.append({"method": name, "trial": label["trial"], "criterion_id": label["criterion_id"],
                         "expected": label["expected"], "predicted": predicted, "match": predicted == label["expected"],
                         "judgment_call": label["judgment_call"], "flags": flags, "explanation": reviewed[0].explanation})
        results[name] = score(pairs)

    report = {"label_status": labels["label_status"], "results": results, "rows": rows}
    report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    title = "# Criterion evaluation" + (" (held-out)" if suffix else "")
    lines = [title, "", f"Labels: {len(labels['labels'])} criteria ({args.labels.name}). {labels['label_status']}.", "",
             "| Method | Accuracy | Decidable correct | Unsafe false clearance | UNKNOWN to MEETS | False exclusion |", "|---|---|---|---|---|---|"]
    for name, r in results.items():
        lines.append(f"| {name} | {r['accuracy']:.2f} | {r['decided_correctly']:.2f} ({r['decidable_labels']}) | {r['unsafe_false_clearance']} | {r['unknown_to_meets']} | {r['false_exclusion']} |")
    lines += ["", "## Mismatches", ""]
    for row in rows:
        if not row["match"]:
            note = " (judgment call)" if row["judgment_call"] else ""
            lines.append(f"- {row['method']} · {row['trial']} {row['criterion_id']}: expected {row['expected']}, got {row['predicted']}{note}")
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
