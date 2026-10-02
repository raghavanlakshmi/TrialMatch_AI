"""Tests for the frozen ClinicalTrials.gov snapshot downloader."""

import json
from pathlib import Path

import pytest
import requests

from scripts.download_trials import (
    TrialDownloadError,
    _matches_selection,
    collect_snapshot,
    iter_studies,
    normalize_study,
    write_snapshot,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def study(
    nct_id: str,
    *,
    status: str = "RECRUITING",
    conditions: list[str] | None = None,
    criteria: str | None = "Inclusion Criteria:\n* Synthetic criterion",
    title: str | None = None,
) -> dict:
    eligibility = {"minimumAge": "18 Years", "maximumAge": "80 Years", "sex": "ALL"}
    if criteria is not None:
        eligibility["eligibilityCriteria"] = criteria
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id, "briefTitle": title or f"Study {nct_id}"},
            "statusModule": {
                "overallStatus": status,
                "lastUpdatePostDateStruct": {"date": "2026-09-15"},
            },
            "conditionsModule": {"conditions": conditions or ["Colorectal Cancer"]},
            "descriptionModule": {"briefSummary": "Synthetic trial summary."},
            "eligibilityModule": eligibility,
            "contactsLocationsModule": {
                "locations": [{"facility": "Synthetic Center", "city": "Boston", "country": "United States"}]
            },
            "armsInterventionsModule": {
                "interventions": [{"type": "DRUG", "name": "Synthetic Drug"}]
            },
        }
    }


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("synthetic HTTP failure")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        token = params.get("pageToken")
        return FakeResponse(self.pages[token])


def test_normalize_study_keeps_source_fields_and_exact_criteria():
    criteria = "Inclusion Criteria:\n* KRAS G12C mutation\n\nExclusion Criteria:\n* Prior therapy"
    record = normalize_study(study("NCT12345678", criteria=criteria), "2026-10-02")
    assert record == {
        "nct_id": "NCT12345678",
        "title": "Study NCT12345678",
        "overall_status": "RECRUITING",
        "conditions": ["Colorectal Cancer"],
        "brief_summary": "Synthetic trial summary.",
        "eligibility_criteria": criteria,
        "minimum_age": "18 Years",
        "maximum_age": "80 Years",
        "sex": "ALL",
        "locations": [{"facility": "Synthetic Center", "city": "Boston", "country": "United States"}],
        "interventions": [{"type": "DRUG", "name": "Synthetic Drug"}],
        "source_url": "https://clinicaltrials.gov/study/NCT12345678",
        "last_updated": "2026-09-15",
        "snapshot_date": "2026-10-02",
    }


@pytest.mark.parametrize(
    "record",
    [
        study("NCT12345678", criteria=None),
        study("NCT12345678", criteria="  "),
        study("NCT12345678", status="ACTIVE_NOT_RECRUITING"),
    ],
)
def test_unusable_or_nonrecruiting_studies_are_skipped(record):
    assert normalize_study(record, "2026-10-02") is None


@pytest.mark.parametrize("nct_id", ["12345678", "NCT123", "NCTabcdefgh"])
def test_invalid_nct_id_is_rejected(nct_id):
    with pytest.raises(TrialDownloadError, match="invalid NCT identifier"):
        normalize_study(study(nct_id), "2026-10-02")


def test_pagination_uses_next_page_token_without_mutating_query():
    pages = {
        None: {"studies": [study("NCT00000001")], "nextPageToken": "page-two"},
        "page-two": {"studies": [study("NCT00000002")]},
    }
    session = FakeSession(pages)
    query = {"query.cond": "colorectal cancer"}
    results = list(iter_studies(session, query, page_size=1))
    assert [item["protocolSection"]["identificationModule"]["nctId"] for item in results] == [
        "NCT00000001", "NCT00000002"
    ]
    assert query == {"query.cond": "colorectal cancer"}
    assert session.calls[0]["params"]["filter.overallStatus"] == "RECRUITING"
    assert session.calls[0]["params"]["pageSize"] == 1
    assert "pageToken" not in session.calls[0]["params"]
    assert session.calls[1]["params"]["pageToken"] == "page-two"


def test_repeated_pagination_token_is_rejected():
    session = FakeSession({
        None: {"studies": [], "nextPageToken": "repeat"},
        "repeat": {"studies": [], "nextPageToken": "repeat"},
    })
    with pytest.raises(TrialDownloadError, match="repeated pagination token"):
        list(iter_studies(session, {}, page_size=1))


def test_distractor_filters_are_explicit():
    pancreatic = normalize_study(
        study("NCT00000001", conditions=["Pancreatic Cancer"]), "2026-10-02"
    )
    colorectal_overlap = normalize_study(
        study("NCT00000002", conditions=["Pancreatic Cancer", "Colorectal Cancer"]), "2026-10-02"
    )
    assert _matches_selection(pancreatic, {"selection_filter": "exclude_colorectal_conditions"})
    assert not _matches_selection(
        colorectal_overlap, {"selection_filter": "exclude_colorectal_conditions"}
    )
    g12d = normalize_study(
        study("NCT00000003", criteria="KRAS G12D mutation required"), "2026-10-02"
    )
    mixed = normalize_study(
        study("NCT00000004", criteria="KRAS G12D or KRAS G12C mutation"), "2026-10-02"
    )
    assert _matches_selection(g12d, {"selection_filter": "g12d_without_g12c"})
    assert not _matches_selection(mixed, {"selection_filter": "g12d_without_g12c"})


def test_collection_deduplicates_nct_ids_and_records_query_matches():
    session = FakeSession({
        None: {
            "studies": [study("NCT00000001"), study("NCT00000002")]
        }
    })
    queries = (
        {"name": "first", "role": "candidate", "params": {}, "limit": 2},
        {"name": "second", "role": "distractor", "params": {}, "limit": 1},
    )
    records, manifest = collect_snapshot(
        session, "2026-10-02", queries=queries,
        page_size=100, minimum_records=2, maximum_records=3,
    )
    assert [record["nct_id"] for record in records] == ["NCT00000001", "NCT00000002"]
    assert records[0]["selection_role"] == "candidate"
    assert records[0]["matched_queries"] == ["first", "second"]
    assert manifest["record_count"] == 2
    assert manifest["role_counts"] == {"candidate": 2}
    assert manifest["snapshot_date"] == "2026-10-02"


def test_collection_refuses_out_of_range_snapshot():
    session = FakeSession({None: {"studies": [study("NCT00000001")]}})
    queries = ({"name": "small", "role": "candidate", "params": {}, "limit": 1},)
    with pytest.raises(TrialDownloadError, match="expected 2–3"):
        collect_snapshot(
            session, "2026-10-02", queries=queries,
            minimum_records=2, maximum_records=3,
        )


def test_snapshot_write_is_jsonl_and_requires_explicit_overwrite(tmp_path):
    records = [{"nct_id": "NCT00000001", "eligibility_criteria": "Exact source text"}]
    manifest = {"snapshot_date": "2026-10-02", "record_count": 1}
    write_snapshot(records, manifest, tmp_path)
    lines = (tmp_path / "trials.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == records
    assert json.loads((tmp_path / "snapshot_manifest.json").read_text(encoding="utf-8")) == manifest
    assert not list(tmp_path.glob("*.tmp"))
    with pytest.raises(TrialDownloadError, match="already exists"):
        write_snapshot(records, manifest, tmp_path)
    changed = [{"nct_id": "NCT00000002", "eligibility_criteria": "Replacement"}]
    write_snapshot(changed, manifest, tmp_path, overwrite=True)
    assert json.loads((tmp_path / "trials.jsonl").read_text(encoding="utf-8")) == changed[0]


def test_invalid_page_size_and_snapshot_date_are_rejected():
    session = FakeSession({None: {"studies": []}})
    with pytest.raises(TrialDownloadError, match="page_size"):
        collect_snapshot(session, "2026-10-02", page_size=0)
    with pytest.raises(ValueError):
        collect_snapshot(session, "not-a-date")


def test_frozen_snapshot_is_complete_unique_and_reproducible():
    trial_dir = PROJECT_ROOT / "data" / "trials"
    records = [
        json.loads(line)
        for line in (trial_dir / "trials.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    manifest = json.loads(
        (trial_dir / "snapshot_manifest.json").read_text(encoding="utf-8")
    )
    required_fields = {
        "nct_id", "title", "overall_status", "conditions", "brief_summary",
        "eligibility_criteria", "minimum_age", "maximum_age", "sex", "locations",
        "source_url", "last_updated", "snapshot_date",
    }
    assert 50 <= len(records) <= 100
    assert len({record["nct_id"] for record in records}) == len(records)
    assert all(required_fields <= record.keys() for record in records)
    assert all(record["overall_status"] == "RECRUITING" for record in records)
    assert all(record["snapshot_date"] == manifest["snapshot_date"] for record in records)
    assert all(record["eligibility_criteria"].strip() for record in records)
    assert all(
        record["source_url"] == f"https://clinicaltrials.gov/study/{record['nct_id']}"
        for record in records
    )
    assert manifest["record_count"] == len(records)
    assert sum(manifest["role_counts"].values()) == len(records)
    assert manifest["role_counts"]["candidate"] > 0
    assert manifest["role_counts"]["distractor"] > 0
