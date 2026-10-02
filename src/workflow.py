"""LangGraph orchestration for the bounded prescreening workflow."""

from __future__ import annotations

from time import perf_counter
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .criteria import load_criteria
from .document_ingestion import ingest_documents
from .eligibility import assess_trial, summarize_trial
from .evidence_extraction import extract_evidence, verify_quotes
from .evidence_view import build_evidence_groups
from .observability import utc_now
from .retrieval import BM25Retriever, RetrievalError, compact_patient_summary, hybrid_search, load_chunks, reciprocal_rank_fusion, rerank_candidates
from .safety import detect_prompt_injection, review_assessments
from .schemas import CriterionAssessment, DocumentPage, EvidenceItem
from .trial_loader import load_trials


class WorkflowState(TypedDict, total=False):
    uploaded_files: list[str]
    pages: list[DocumentPage]
    evidence: list[EvidenceItem]
    patient_summary: str
    candidate_trials: list[dict]
    trial_criteria: dict[str, list]
    assessments: dict[str, list[CriterionAssessment]]
    trial_summaries: dict[str, dict]
    conflicts: list[dict]
    safety_flags: list[str]
    trace: list[dict]
    human_review: dict[str, Any]
    top_k: int


def _run_node(state: WorkflowState, name: str, input_count: int, action):
    started, clock = utc_now(), perf_counter()
    trace = list(state.get("trace", []))
    try:
        updates = action()
        output_count = updates.pop("_output_count", 0)
        status, error = "success", None
    except Exception as exc:
        status, error = "error", f"{type(exc).__name__}: {exc}"
        raise
    finally:
        record = {"step": name, "started_at": started, "ended_at": utc_now(), "latency_ms": round((perf_counter() - clock) * 1000, 2), "input_count": input_count, "output_count": locals().get("output_count", 0), "status": status, "llm_calls": 0}
        if error:
            record["error"] = error
        trace.append(record)
    updates["trace"] = trace
    return updates


def ingest_documents_node(state: WorkflowState):
    def action():
        pages = state.get("pages") or ingest_documents(state.get("uploaded_files", []), use_ocr=True)
        return {"pages": pages, "_output_count": len(pages)}
    return _run_node(state, "ingest_documents", len(state.get("uploaded_files", [])), action)


def extract_evidence_node(state: WorkflowState):
    def action():
        evidence = state.get("evidence") or extract_evidence(state.get("pages", []))
        return {"evidence": evidence, "_output_count": len(evidence)}
    return _run_node(state, "extract_evidence", len(state.get("pages", [])), action)


def verify_quotes_node(state: WorkflowState):
    return _run_node(state, "verify_quotes", len(state.get("evidence", [])), lambda: {"evidence": verify_quotes(state.get("evidence", []), state.get("pages", [])), "_output_count": len(state.get("evidence", []))})


def detect_conflicts_node(state: WorkflowState):
    def action():
        conflicts = [{"fact": group.key, "values": [item.model_dump() for item in group.items]} for group in build_evidence_groups(state.get("evidence", [])) if group.status == "POTENTIAL_CONFLICT"]
        return {"conflicts": conflicts, "_output_count": len(conflicts)}
    return _run_node(state, "detect_conflicts", len(state.get("evidence", [])), action)


def build_patient_query_node(state: WorkflowState):
    return _run_node(state, "build_patient_query", len(state.get("evidence", [])), lambda: {"patient_summary": compact_patient_summary(state.get("evidence", [])), "_output_count": 1})


def retrieve_trials_node(state: WorkflowState):
    def action():
        query = state.get("patient_summary", "")
        try:
            candidates = hybrid_search(query, state.get("top_k", 5))
            mode = "hybrid_rrf"
        except RetrievalError:
            results = BM25Retriever(load_chunks()).search(query, 20)
            candidates = reciprocal_rank_fusion(results)[:state.get("top_k", 5)]
            mode = "bm25_fallback"
        return {"candidate_trials": [dict(item, retrieval_mode=mode) for item in candidates], "_output_count": len(candidates)}
    return _run_node(state, "retrieve_trials", 1, action)


def rerank_trials_node(state: WorkflowState):
    def action():
        trials = {trial.nct_id: trial for trial in load_trials()}
        candidates = rerank_candidates(state.get("candidate_trials", []), state.get("patient_summary", ""), trials)
        return {"candidate_trials": candidates, "_output_count": len(candidates)}
    return _run_node(state, "rerank_trials", len(state.get("candidate_trials", [])), action)


def load_trial_criteria_node(state: WorkflowState):
    def action():
        all_criteria = load_criteria()
        selected = {c["nct_id"]: all_criteria.get(c["nct_id"], []) for c in state.get("candidate_trials", [])}
        return {"trial_criteria": selected, "_output_count": sum(len(v) for v in selected.values())}
    return _run_node(state, "load_trial_criteria", len(state.get("candidate_trials", [])), action)


def check_structured_rules_node(state: WorkflowState):
    # Age/sex are calculated in assess_trial so each trial receives exactly one result.
    return _run_node(state, "check_structured_rules", len(state.get("candidate_trials", [])), lambda: {"_output_count": len(state.get("candidate_trials", []))})


def assess_criteria_node(state: WorkflowState):
    def action():
        trials = {trial.nct_id: trial for trial in load_trials()}
        assessments, summaries = {}, {}
        for candidate in state.get("candidate_trials", []):
            nct_id = candidate["nct_id"]
            items, summary = assess_trial(trials[nct_id], state.get("trial_criteria", {}).get(nct_id, []), state.get("evidence", []))
            assessments[nct_id], summaries[nct_id] = items, summary
        return {"assessments": assessments, "trial_summaries": summaries, "_output_count": sum(len(v) for v in assessments.values())}
    return _run_node(state, "assess_criteria", sum(len(v) for v in state.get("trial_criteria", {}).values()), action)


def safety_review_node(state: WorkflowState):
    def action():
        flags = list(state.get("safety_flags", []))
        flags += [flag for page in state.get("pages", []) for flag in detect_prompt_injection(page.text)]
        reviewed = {}
        for nct_id, items in state.get("assessments", {}).items():
            reviewed[nct_id], item_flags = review_assessments(items)
            flags.extend(item_flags)
        summaries = {nct_id: summarize_trial(items) for nct_id, items in reviewed.items()}
        return {"assessments": reviewed, "trial_summaries": summaries, "safety_flags": sorted(set(flags)), "_output_count": len(flags)}
    return _run_node(state, "safety_review", sum(len(v) for v in state.get("assessments", {}).values()), action)


def prepare_human_review_node(state: WorkflowState):
    def action():
        review = {"candidate_trials": state.get("candidate_trials", []), "trial_summaries": state.get("trial_summaries", {}), "requires_human_review": True}
        if not state.get("candidate_trials"):
            review["message"] = "Insufficient information"
        return {"human_review": review, "_output_count": len(state.get("candidate_trials", []))}
    return _run_node(state, "prepare_human_review", len(state.get("candidate_trials", [])), action)


def _has_candidates(state: WorkflowState) -> str:
    return "rerank" if state.get("candidate_trials") else "review"


def build_workflow():
    graph = StateGraph(WorkflowState)
    nodes = {
        "ingest_documents": ingest_documents_node, "extract_evidence": extract_evidence_node,
        "verify_quotes": verify_quotes_node, "detect_conflicts": detect_conflicts_node,
        "build_patient_query": build_patient_query_node, "retrieve_trials": retrieve_trials_node,
        "rerank_trials": rerank_trials_node, "load_trial_criteria": load_trial_criteria_node,
        "check_structured_rules": check_structured_rules_node, "assess_criteria": assess_criteria_node,
        "safety_review": safety_review_node, "prepare_human_review": prepare_human_review_node,
    }
    for name, function in nodes.items():
        graph.add_node(name, function)
    graph.add_edge(START, "ingest_documents")
    chain = ["ingest_documents", "extract_evidence", "verify_quotes", "detect_conflicts", "build_patient_query", "retrieve_trials"]
    for left, right in zip(chain, chain[1:]):
        graph.add_edge(left, right)
    graph.add_conditional_edges("retrieve_trials", _has_candidates, {"rerank": "rerank_trials", "review": "prepare_human_review"})
    tail = ["rerank_trials", "load_trial_criteria", "check_structured_rules", "assess_criteria", "safety_review", "prepare_human_review"]
    for left, right in zip(tail, tail[1:]):
        graph.add_edge(left, right)
    graph.add_edge("prepare_human_review", END)
    return graph.compile()
