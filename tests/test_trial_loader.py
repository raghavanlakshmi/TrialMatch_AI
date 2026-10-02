"""Tests for age parsing, trial validation, and searchable text."""

import json
from pathlib import Path

import pytest

from src.trial_loader import (
    DEFAULT_MANIFEST_PATH,
    DEFAULT_TRIALS_PATH,
    TrialLoadError,
    build_searchable_text,
    load_trials,
    normalized_trial_record,
    parse_age_to_years,
    write_normalized_trials,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (None, None),
        ("18 Years", 18.0),
        ("1 Year", 1.0),
        ("6 Months", 0.5),
        ("1 Month", round(1 / 12, 8)),
        ("2 Weeks", round(14 / 365.2425, 8)),
        ("1 Day", round(1 / 365.2425, 8)),
        ("24 Hours", round(1 / 365.2425, 8)),
        ("60 Minutes", round(1 / (365.2425 * 24), 8)),
    ],
)
def test_parse_age_to_years(source, expected):
    assert parse_age_to_years(source) == expected


@pytest.mark.parametrize("source", ["", "Adult", "18", "Years 18", -1, True])
def test_invalid_age_strings_are_rejected(source):
    with pytest.raises(TrialLoadError, match="Age|Unsupported"):
        parse_age_to_years(source)


def test_frozen_snapshot_loads_with_parsed_age_fields():
    trials = load_trials()
    assert len(trials) == 75
    assert len({trial.nct_id for trial in trials}) == 75
    assert all(trial.overall_status == "RECRUITING" for trial in trials)
    assert all(trial.eligibility_criteria.strip() for trial in trials)
    assert all(trial.snapshot_date == "2026-10-02" for trial in trials)
    for trial in trials:
        assert trial.minimum_age_years == parse_age_to_years(trial.minimum_age)
        assert trial.maximum_age_years == parse_age_to_years(trial.maximum_age)
        if trial.minimum_age_years is not None and trial.maximum_age_years is not None:
            assert trial.minimum_age_years <= trial.maximum_age_years


def test_searchable_text_contains_complete_source_sections():
    trial = load_trials()[0]
    text = build_searchable_text(trial)
    assert text.startswith(f"NCT ID: {trial.nct_id}\nTitle: {trial.title}")
    assert f"Conditions: {'; '.join(trial.conditions)}" in text
    assert "\nStatus: RECRUITING\n" in text
    assert "\nSummary: " in text
    assert "\nEligibility:\n" in text
    assert text.endswith(trial.eligibility_criteria.strip())
    assert normalized_trial_record(trial)["searchable_text"] == text


def test_load_reports_bad_json_line(tmp_path):
    source = tmp_path / "trials.jsonl"
    source.write_text('{"valid": true}\nnot-json\n', encoding="utf-8")
    with pytest.raises(TrialLoadError, match="line 1|line 2"):
        load_trials(source, manifest_path=None)


def test_load_rejects_duplicate_nct_id(tmp_path):
    trial = load_trials()[0].model_dump(exclude={"minimum_age_years", "maximum_age_years"})
    source = tmp_path / "trials.jsonl"
    source.write_text(
        json.dumps(trial) + "\n" + json.dumps(trial) + "\n", encoding="utf-8"
    )
    with pytest.raises(TrialLoadError, match="Duplicate trial identifier"):
        load_trials(source, manifest_path=None)


def test_load_rejects_source_url_mismatch_and_reversed_age_range(tmp_path):
    raw = json.loads(DEFAULT_TRIALS_PATH.read_text(encoding="utf-8").splitlines()[0])
    bad_url = dict(raw, source_url="https://clinicaltrials.gov/study/NCT99999999")
    source = tmp_path / "bad-url.jsonl"
    source.write_text(json.dumps(bad_url) + "\n", encoding="utf-8")
    with pytest.raises(TrialLoadError, match="source URL"):
        load_trials(source, manifest_path=None)
    reversed_age = dict(raw, minimum_age="80 Years", maximum_age="18 Years")
    source.write_text(json.dumps(reversed_age) + "\n", encoding="utf-8")
    with pytest.raises(TrialLoadError, match="minimum age exceeds maximum age"):
        load_trials(source, manifest_path=None)


def test_manifest_count_and_date_are_checked(tmp_path):
    trial = json.loads(DEFAULT_TRIALS_PATH.read_text(encoding="utf-8").splitlines()[0])
    source = tmp_path / "trials.jsonl"
    source.write_text(json.dumps(trial) + "\n", encoding="utf-8")
    manifest = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["record_count"] = 2
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(TrialLoadError, match="Trial count"):
        load_trials(source, manifest_path=manifest_path)


def test_normalized_jsonl_preserves_source_and_adds_derived_fields(tmp_path):
    trials = load_trials()[:2]
    destination = tmp_path / "normalized.jsonl"
    write_normalized_trials(trials, destination)
    records = [json.loads(line) for line in destination.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2
    for trial, record in zip(trials, records):
        assert record["nct_id"] == trial.nct_id
        assert record["eligibility_criteria"] == trial.eligibility_criteria
        assert record["minimum_age"] == trial.minimum_age
        assert record["minimum_age_years"] == trial.minimum_age_years
        assert record["searchable_text"] == build_searchable_text(trial)
    with pytest.raises(TrialLoadError, match="already exists"):
        write_normalized_trials(trials, destination)
    write_normalized_trials(trials, destination, overwrite=True)
    assert not destination.with_suffix(".jsonl.tmp").exists()
