"""Prepare traceable evidence groups for the synthetic patient review view."""

from collections.abc import Iterable
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import ValidationError

from .config import FACTS_TO_LOOK_FOR
from .evidence_extraction import EvidenceExtractionError, verify_quotes
from .schemas import DocumentPage, EvidenceItem


class EvidenceViewError(ValueError):
    """The prepared evidence cannot be loaded for review."""


@dataclass
class EvidenceGroup:
    key: str
    label: str
    items: list[EvidenceItem]
    status: Literal["UNKNOWN", "POTENTIAL_CONFLICT"] | None

    @property
    def has_unverified_quotes(self) -> bool:
        return any(not item.quote_verified for item in self.items)


DISPLAY_ORDER = (
    "diagnosis", "metastatic_site", "ecog", "kras_status", "msi_status",
    "prior_kras_g12c_inhibitor", "prior_therapies", "age", "sex", "anc",
    "braf_status", "hemoglobin", "creatinine",
)
SCALAR_FACTS = frozenset({
    "age", "sex", "diagnosis", "ecog", "kras_status", "msi_status", "anc",
    "braf_status", "hemoglobin", "creatinine", "cancer_stage",
})
EXTRA_LABELS = {
    "metastatic_site": "Metastatic site", "braf_status": "BRAF status",
    "hemoglobin": "Hemoglobin", "creatinine": "Creatinine",
    "cancer_stage": "Cancer stage", "current_medication": "Current medications",
    "comorbidity": "Comorbidities", "other_biomarker": "Other biomarkers",
    "other_lab": "Other laboratory evidence", "other_performance": "Other performance status",
}


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def _checklist_keys(item: EvidenceItem) -> list[str]:
    text = _normalize(f"{item.value} {item.evidence_text}")
    if item.category in {"age", "sex", "diagnosis"}:
        return [item.category]
    if item.category == "biomarker":
        if re.search(r"\bkras\b", text):
            return ["kras_status"]
        if re.search(r"\b(msi|mss)\b|microsatellite", text):
            return ["msi_status"]
    if item.category == "performance_status" and re.search(r"\becog\b", text):
        return ["ecog"]
    if item.category == "lab" and re.search(r"\banc\b|absolute neutrophil count", text):
        return ["anc"]
    if item.category == "prior_treatment":
        keys = ["prior_therapies"]
        if re.search(r"\bkras\s+g12c\s+inhibitor\b", text):
            keys.append("prior_kras_g12c_inhibitor")
        return keys
    return []


def _extra_key(item: EvidenceItem) -> str:
    text = _normalize(f"{item.value} {item.evidence_text}")
    if item.category == "biomarker":
        return "braf_status" if re.search(r"\bbraf\b", text) else "other_biomarker"
    if item.category == "lab":
        if "hemoglobin" in text:
            return "hemoglobin"
        return "creatinine" if "creatinine" in text else "other_lab"
    if item.category == "performance_status":
        return "other_performance"
    return item.category


def _comparison_value(key: str, item: EvidenceItem) -> str:
    """Compare explicit values; retain every original record for the reviewer."""
    value = _normalize(item.value)
    if key == "ecog":
        match = re.fullmatch(r"(?:ecog\s*[:=]?\s*)?(\d+)", value)
        if match:
            return match.group(1)
    if key == "age":
        match = re.fullmatch(r"(?:age\s*[:=]?\s*)?(\d+)\s*(?:years?|years? old)?", value)
        if match:
            return match.group(1)
    if key == "kras_status":
        # The guide explicitly supplies these two wordings for the same result.
        if re.fullmatch(r"kras\s*:?\s*g12c\s*(?:\+|mutation detected)", value):
            return "kras g12c positive"
    if key == "msi_status" and re.fullmatch(
        r"(?:msi\s*:?\s*)?(?:microsatellite stable(?:\s*\(mss\))?|mss)", value
    ):
        return "microsatellite stable"
    return value


def build_evidence_groups(evidence: Iterable[EvidenceItem]) -> list[EvidenceGroup]:
    """Include all checklist facts; missing verified support remains UNKNOWN."""
    grouped = {key: [] for key in FACTS_TO_LOOK_FOR}
    for item in evidence:
        keys = _checklist_keys(item) or [_extra_key(item)]
        for key in keys:
            grouped.setdefault(key, []).append(item)
    groups = []
    for key, items in grouped.items():
        label = FACTS_TO_LOOK_FOR.get(key) or EXTRA_LABELS.get(key, key.replace("_", " ").title())
        if key == "ecog":
            label = "Performance status (ECOG)"
        status = None
        if not any(item.quote_verified for item in items):
            status = "UNKNOWN"
        elif key in SCALAR_FACTS and len({_comparison_value(key, item) for item in items}) > 1:
            status = "POTENTIAL_CONFLICT"
        groups.append(EvidenceGroup(key, label, items, status))
    order = {key: index for index, key in enumerate(DISPLAY_ORDER)}
    groups.sort(key=lambda group: order.get(group.key, len(order)))
    return groups


def load_prepared_evidence(project_root: Path) -> tuple[list[EvidenceItem], list[DocumentPage]]:
    """Recompute saved verification flags against the saved source page text."""
    output_dir = project_root / "data" / "sample_outputs"
    try:
        raw_evidence = json.loads((output_dir / "SYN-001_evidence.json").read_text(encoding="utf-8"))
        raw_pages = json.loads((output_dir / "SYN-001_document_pages_with_ocr.json").read_text(encoding="utf-8"))
        if not isinstance(raw_evidence, list) or not isinstance(raw_pages, list):
            raise EvidenceViewError("Prepared evidence and source pages must be lists.")
        evidence = [EvidenceItem.model_validate(record) for record in raw_evidence]
        pages = [DocumentPage.model_validate(record) for record in raw_pages]
        return verify_quotes(evidence, pages), pages
    except EvidenceViewError:
        raise
    except (OSError, ValueError, ValidationError, EvidenceExtractionError):
        raise EvidenceViewError(
            "Prepared evidence could not be loaded. Check the saved ingestion and extraction results."
        ) from None


def source_file_path(patient_dir: Path, filename: str) -> Path | None:
    """Only expose source files within this patient's document folder."""
    if not filename or Path(filename).name != filename or "\\" in filename:
        return None
    root = patient_dir.resolve()
    path = (root / filename).resolve()
    if root not in path.parents or not path.is_file():
        return None
    if path.suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg", ".txt"}:
        return None
    return path
