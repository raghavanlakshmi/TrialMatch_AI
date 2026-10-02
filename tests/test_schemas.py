"""Evidence records require traceable source support and start unverified."""

import pytest
from pydantic import ValidationError

from src.schemas import EvidenceItem


@pytest.fixture
def source_fact():
    return {
        "category": "performance_status",
        "value": "ECOG 1",
        "source_file": "oncology_note.pdf",
        "source_page": 2,
        "evidence_text": "Performance status: ECOG 1",
    }


def test_supported_fact_starts_unverified_and_keeps_unknown_metadata(source_fact):
    item = EvidenceItem(**source_fact)
    assert item.quote_verified is False
    assert item.date is None and item.normalized_value is None
    assert item.model_dump()["source_page"] == 2


def test_schema_preserves_exact_quote_whitespace_and_case(source_fact):
    source_fact["evidence_text"] = "  Performance status:\nECOG 1\t"
    item = EvidenceItem(**source_fact, date="2026-03-10", normalized_value="1")
    assert item.evidence_text == source_fact["evidence_text"]
    assert item.date == "2026-03-10" and item.normalized_value == "1"
    assert EvidenceItem.model_validate_json(item.model_dump_json()) == item


@pytest.mark.parametrize("field", ["source_file", "source_page", "evidence_text"])
def test_missing_source_or_quote_is_rejected(source_fact, field):
    source_fact.pop(field)
    with pytest.raises(ValidationError):
        EvidenceItem(**source_fact)


@pytest.mark.parametrize("field", ["source_file", "evidence_text", "value"])
def test_whitespace_cannot_stand_in_for_patient_evidence(source_fact, field):
    source_fact[field] = " \n\t"
    with pytest.raises(ValidationError, match="must not be blank"):
        EvidenceItem(**source_fact)


@pytest.mark.parametrize("page_number", [0, -1, True, "2"])
def test_provenance_requires_positive_integer_page(source_fact, page_number):
    source_fact["source_page"] = page_number
    with pytest.raises(ValidationError):
        EvidenceItem(**source_fact)


def test_confidence_and_unsupported_categories_are_rejected(source_fact):
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvidenceItem(**source_fact, confidence=0.99)
    source_fact["category"] = "clinical_interpretation"
    with pytest.raises(ValidationError):
        EvidenceItem(**source_fact)


def test_validated_record_cannot_lose_its_source_page_after_creation(source_fact):
    item = EvidenceItem(**source_fact)
    with pytest.raises(ValidationError):
        item.source_page = 0
    assert item.source_page == 2
