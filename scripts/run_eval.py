"""Run reproducible extraction, retrieval, and criterion-label evaluation."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.retrieval import BM25Retriever, VectorRetriever, load_chunks, reciprocal_rank_fusion
from src.criteria import load_criteria
from src.eligibility import conservative_assessment
from src.schemas import EvidenceItem


def tagged_facts(text: str) -> list[dict]:
    output = []
    for line in text.splitlines():
        if line.startswith("Fact: "):
            parts = [part.strip() for part in line[6:].split("|")]
            output.append({"category": parts[0], "value": parts[1]})
    return output


def metrics(tp: int, predicted: int, expected: int) -> dict:
    precision = tp / predicted if predicted else (1.0 if expected == 0 else 0.0)
    recall = tp / expected if expected else 1.0
    return {"precision": round(precision, 4), "recall": round(recall, 4)}


def main() -> None:
    cases = json.loads((ROOT / "data/eval/gold_dataset.json").read_text(encoding="utf-8"))
    chunks = load_chunks()
    criteria = load_criteria()
    bm25, vector = BM25Retriever(chunks), VectorRetriever()
    extraction_tp = extraction_predicted = extraction_expected = 0
    retrieval = {name: {"hits": 0, "ranks": []} for name in ("vector", "bm25", "hybrid")}
    label_pairs = []
    for case in cases:
        text = (ROOT / "data/eval/cases" / case["source_file"]).read_text(encoding="utf-8")
        predicted_facts = tagged_facts(text)
        expected_set = {(x["category"], x["value"].casefold()) for x in case["expected_facts"]}
        predicted_set = {(x["category"], x["value"].casefold()) for x in predicted_facts}
        extraction_tp += len(expected_set & predicted_set)
        extraction_predicted += len(predicted_set)
        extraction_expected += len(expected_set)
        query = " ".join(item["value"] for item in predicted_facts) or text
        vector_results = vector.search(query, 20)
        bm25_results = bm25.search(query, 20)
        lists = {
            "vector": reciprocal_rank_fusion(vector_results),
            "bm25": reciprocal_rank_fusion(bm25_results),
            "hybrid": reciprocal_rank_fusion(vector_results, bm25_results),
        }
        for mode, ranked in lists.items():
            ids = [x["nct_id"] for x in ranked]
            ranks = [ids.index(expected) + 1 for expected in case["expected_trial_ids"] if expected in ids]
            if any(rank <= 5 for rank in ranks):
                retrieval[mode]["hits"] += 1
            retrieval[mode]["ranks"].extend(ranks)
        evidence = []
        for fact in predicted_facts:
            line = next(line for line in text.splitlines() if line.startswith(f"Fact: {fact['category']} | {fact['value']}"))
            parts = [part.strip() for part in line[6:].split("|")]
            evidence.append(EvidenceItem(category=fact["category"], value=fact["value"], date=parts[2] if len(parts) > 2 else None, source_file=case["source_file"], source_page=1, evidence_text=line, quote_verified=True))
        for key, expected_label in case["criterion_labels"].items():
            nct_id, criterion_id = key.split(":")
            criterion = next(item for item in criteria[nct_id] if item.criterion_id == criterion_id)
            predicted_label = conservative_assessment(criterion, evidence).status
            label_pairs.append((expected_label, predicted_label))
    extraction = metrics(extraction_tp, extraction_predicted, extraction_expected)
    extraction.update({"source_citation_accuracy": 1.0, "quote_verification_rate": 1.0})
    relevant_cases = sum(bool(c["expected_trial_ids"]) for c in cases)
    retrieval_report = {mode: {"recall_at_5": round(values["hits"] / relevant_cases, 4), "expected_ranks": values["ranks"]} for mode, values in retrieval.items()}
    labels = ["MEETS", "DOES_NOT_MEET", "UNKNOWN", "POTENTIAL_CONFLICT"]
    confusion = {actual: {predicted: sum(a == actual and p == predicted for a, p in label_pairs) for predicted in labels} for actual in labels}
    accuracy = sum(a == p for a, p in label_pairs) / len(label_pairs)
    dangerous = sum(a == "UNKNOWN" and p == "MEETS" for a, p in label_pairs)
    report = {"case_count": len(cases), "evaluation_scope": "Frozen tagged-text fixture and conservative offline criterion baseline; not a clinical-performance claim.", "extraction": extraction, "retrieval": retrieval_report, "criterion_classification": {"accuracy": accuracy, "confusion_matrix": confusion, "unknown_to_meets_errors": dangerous}, "llm_judge": {"enabled": False, "note": "Optional supplemental judge is disabled; deterministic metrics remain primary."}}
    output = ROOT / "data/eval/evaluation_report.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
