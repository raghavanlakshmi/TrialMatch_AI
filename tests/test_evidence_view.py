"""Check missing-data display, conflict retention, source access, and the UI."""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.config import FACTS_TO_LOOK_FOR
from src.evidence_view import (
    EvidenceViewError, build_evidence_groups, load_prepared_evidence, source_file_path,
)
from src.schemas import EvidenceItem


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def record(value="ECOG 1", **overrides):
    data = {
        "category": "performance_status", "value": value,
        "source_file": "oncology_note.pdf", "source_page": 2,
        "date": "2026-03-10", "evidence_text": value, "quote_verified": True,
    }
    data.update(overrides)
    return EvidenceItem(**data)


def by_key(items):
    return {group.key: group for group in build_evidence_groups(items)}


def test_prepared_patient_has_one_ecog_conflict_and_one_unknown_fact():
    evidence, pages = load_prepared_evidence(PROJECT_ROOT)
    groups = build_evidence_groups(evidence)
    assert len(evidence) == 16 and len(pages) == 7
    assert [group.key for group in groups if group.status == "POTENTIAL_CONFLICT"] == ["ecog"]
    assert [group.key for group in groups if group.status == "UNKNOWN"] == ["prior_kras_g12c_inhibitor"]
    ecog = next(group for group in groups if group.key == "ecog")
    assert [item.value for item in ecog.items] == ["ECOG 1", "ECOG 1", "ECOG 2"]
    assert all(item.quote_verified for item in evidence)


def test_all_checklist_facts_remain_unknown_with_no_evidence():
    groups = by_key([])
    assert set(groups) == set(FACTS_TO_LOOK_FOR)
    assert all(group.status == "UNKNOWN" and group.items == [] for group in groups.values())


def test_mutation_does_not_become_prior_inhibitor_history():
    items = [
        record("KRAS G12C+", category="biomarker"),
        record("FOLFOX, then FOLFIRI", category="prior_treatment"),
    ]
    groups = by_key(items)
    assert groups["kras_status"].status is None
    assert groups["prior_therapies"].status is None
    assert groups["prior_kras_g12c_inhibitor"].status == "UNKNOWN"
    assert groups["prior_kras_g12c_inhibitor"].items == []


@pytest.mark.parametrize("date", ["2026-03-10", "2026-03-11", "2020-01-01"])
def test_differing_ecog_values_are_flagged_regardless_of_dates(date):
    first = record()
    second = record("ECOG 2", date=date, source_file="referral.png", source_page=1)
    group = by_key([first, second])["ecog"]
    assert group.status == "POTENTIAL_CONFLICT"
    assert group.items == [first, second]
    assert group.items[1].date == date


def test_same_ecog_value_in_multiple_sources_does_not_make_a_conflict():
    group = by_key([record(), record("ecog 1", source_file="note.png", source_page=1)])["ecog"]
    assert group.status is None
    assert len(group.items) == 2


def test_explicit_guide_kras_aliases_keep_both_records_without_false_conflict():
    items = [record("KRAS G12C+", category="biomarker"), record("KRAS: G12C mutation detected", category="biomarker")]
    group = by_key(items)["kras_status"]
    assert group.status is None and group.items == items
    different = record("KRAS G12D mutation detected", category="biomarker")
    assert by_key(items + [different])["kras_status"].status == "POTENTIAL_CONFLICT"


def test_complementary_treatment_entries_are_preserved():
    items = [record("FOLFOX completed", category="prior_treatment"), record("FOLFOX, then FOLFIRI", category="prior_treatment")]
    group = by_key(items)["prior_therapies"]
    assert group.items == items and group.status is None


def test_unverified_claim_does_not_fill_missing_checklist_fact():
    item = record("Prior KRAS G12C inhibitor: none", category="prior_treatment", quote_verified=False)
    group = by_key([item])["prior_kras_g12c_inhibitor"]
    assert group.status == "UNKNOWN"
    assert group.has_unverified_quotes
    assert group.items == [item]


def test_stored_verification_flag_is_recomputed_from_source_pages(tmp_path):
    output = tmp_path / "data" / "sample_outputs"
    output.mkdir(parents=True)
    (output / "SYN-001_evidence.json").write_text(json.dumps([record().model_dump()]), encoding="utf-8")
    (output / "SYN-001_document_pages_with_ocr.json").write_text(json.dumps([{
        "filename": "oncology_note.pdf", "page_number": 2,
        "text": "Different page text", "extraction_method": "PYMUPDF",
    }]), encoding="utf-8")
    evidence, _ = load_prepared_evidence(tmp_path)
    assert not evidence[0].quote_verified


def test_missing_or_invalid_saved_data_has_clear_error(tmp_path):
    with pytest.raises(EvidenceViewError, match="Prepared evidence could not be loaded"):
        load_prepared_evidence(tmp_path)


def test_source_preview_cannot_escape_patient_folder(tmp_path):
    root = tmp_path / "patient"
    root.mkdir()
    (root / "note.png").write_bytes(b"synthetic image placeholder")
    (tmp_path / "private.txt").write_text("private", encoding="utf-8")
    assert source_file_path(root, "note.png") == root / "note.png"
    for filename in ["../private.txt", "..\\private.txt", str(tmp_path / "private.txt"), "missing.pdf"]:
        assert source_file_path(root, filename) is None


def test_streamlit_view_shows_patient_sources_conflict_and_unknown():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=15)
    assert not app.exception
    assert app.title[0].value == "TrialMatch AI"
    assert [metric.value for metric in app.metric] == ["16", "1", "1"]
    assert any("Potential conflict" in warning.value for warning in app.warning)
    assert any("UNKNOWN — no supporting evidence" in info.value for info in app.info)
    texts = [text.value for text in app.text]
    assert "Metastatic colorectal adenocarcinoma" in texts
    assert "ECOG 1" in texts and "ECOG 2" in texts
    assert any("oncology_note.pdf · p2 · 2026-03-10" in text for text in texts)
    assert any("outside_referral_scan.png · p1 · 2026-03-11" in text for text in texts)
    assert any("Quote verified" in caption.value for caption in app.caption)


def test_review_filter_keeps_conflict_and_missing_fact_visible():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=15)
    app.checkbox[0].check().run(timeout=15)
    assert not app.exception
    assert [heading.value for heading in app.subheader] == [
        "Performance status (ECOG)", "Prior KRAS G12C inhibitor",
    ]
    assert any("ECOG 2" == text.value for text in app.text)
