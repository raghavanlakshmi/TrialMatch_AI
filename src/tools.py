"""Bounded data-access tools used by workflow nodes and the criterion agent."""

from __future__ import annotations

import json
from pathlib import Path

from .criteria import load_criteria
from .retrieval import hybrid_search
from .schemas import DocumentPage, EvidenceItem
from .trial_loader import load_trials


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ToolContext:
    """Per-run patient context; source access cannot escape these supplied pages."""

    def __init__(self, evidence: list[EvidenceItem] | None = None, pages: list[DocumentPage] | None = None):
        self.evidence = evidence or []
        self.pages = pages or []

    def get_patient_evidence(self, category: str) -> list[dict]:
        return [item.model_dump() for item in self.evidence if item.category == category]

    def get_source_evidence(self, source_file: str, page: int) -> dict:
        """The sole LLM-callable tool: return one exact supplied source page."""
        matches = [p for p in self.pages if p.filename == source_file and p.page_number == page]
        if len(matches) != 1:
            return {"error": "Source page is unavailable."}
        item = matches[0]
        return {"source_file": item.filename, "page": item.page_number, "text": item.text}


def get_patient_evidence(category: str, evidence: list[EvidenceItem]) -> list[dict]:
    return ToolContext(evidence=evidence).get_patient_evidence(category)


def search_trials(query: str, top_k: int = 10) -> list[dict]:
    return hybrid_search(query, top_k)


def get_trial(nct_id: str) -> dict | None:
    trial = next((item for item in load_trials() if item.nct_id == nct_id), None)
    return trial.model_dump() if trial else None


def get_trial_criteria(nct_id: str) -> list[dict]:
    return [item.model_dump() for item in load_criteria().get(nct_id, [])]


def get_source_evidence(source_file: str, page: int, pages: list[DocumentPage]) -> dict:
    return ToolContext(pages=pages).get_source_evidence(source_file, page)


SOURCE_EVIDENCE_TOOL = {
    "type": "function",
    "name": "get_source_evidence",
    "description": "Retrieve the exact text of one supplied patient source page when a cited evidence quote needs inspection.",
    "parameters": {
        "type": "object",
        "properties": {
            "source_file": {"type": "string"},
            "page": {"type": "integer", "minimum": 1},
        },
        "required": ["source_file", "page"],
        "additionalProperties": False,
    },
    "strict": True,
}
