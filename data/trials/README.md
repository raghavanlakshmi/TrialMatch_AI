# Frozen ClinicalTrials.gov snapshot

`trials.jsonl` contains 75 unique studies downloaded from the ClinicalTrials.gov
API v2 on 2026-10-02 (America/New_York). The snapshot contains 55 candidate
records and 20 deliberate distractors. All records had status `RECRUITING` and
nonblank full eligibility criteria when downloaded.

The candidate queries cover colorectal cancer and colorectal cancer with KRAS
G12C. Distractor queries cover pancreatic cancer without colorectal conditions
and KRAS G12D records without KRAS G12C. `selection_role` and `matched_queries`
describe how each record entered this corpus; they are not relevance judgments,
eligibility decisions, or evaluation labels.

Each JSONL record preserves the ClinicalTrials.gov age strings for later parsing
and includes the full eligibility text from
`protocolSection.eligibilityModule.eligibilityCriteria`. It also contains the
study title, recruiting status, conditions, summary, sex, locations,
interventions, source URL, last update date, and snapshot date.

`snapshot_manifest.json` records the source endpoint, query definitions, query
counts, snapshot date, and corpus composition. The application must read this
frozen snapshot at runtime and must not call ClinicalTrials.gov directly.

`normalized_trials.jsonl` is a deterministic derivative used by the later
retrieval pipeline. It retains every source field and adds
`minimum_age_years`, `maximum_age_years`, and `searchable_text`. The source age
strings remain unchanged for auditability. Missing age limits remain null.

To deliberately refresh the snapshot from the repository folder:

```powershell
python scripts/download_trials.py --snapshot-date YYYY-MM-DD --overwrite
```

Refreshing changes an evaluation input. Review the new manifest and rerun the
snapshot tests before accepting it.

After refreshing, regenerate the normalized records:

```powershell
python -m src.trial_loader --overwrite
```
