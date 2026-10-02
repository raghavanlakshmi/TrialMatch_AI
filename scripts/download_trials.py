"""Download a frozen recruiting-trial snapshot from ClinicalTrials.gov API v2."""

import argparse
from collections import Counter
from collections.abc import Iterator
from datetime import date, datetime
import json
import logging
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (  # noqa: E402
    CLINICAL_TRIALS_API_URL,
    TRIAL_QUERIES,
    TRIAL_SNAPSHOT_MAX_RECORDS,
    TRIAL_SNAPSHOT_MIN_RECORDS,
)


LOGGER = logging.getLogger(__name__)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "trials"


class TrialDownloadError(ValueError):
    """No usable frozen snapshot could be created."""


def _module(protocol: dict, name: str) -> dict:
    value = protocol.get(name) or {}
    if not isinstance(value, dict):
        raise TrialDownloadError(f"ClinicalTrials.gov returned an invalid {name}.")
    return value


def normalize_study(study: dict, snapshot_date: str) -> dict | None:
    """Preserve source eligibility text; leave undocumented fields null."""
    protocol = study.get("protocolSection")
    if not isinstance(protocol, dict):
        raise TrialDownloadError("ClinicalTrials.gov returned a study without protocolSection.")
    identity = _module(protocol, "identificationModule")
    nct_id = identity.get("nctId")
    if not isinstance(nct_id, str) or not re.fullmatch(r"NCT\d{8}", nct_id):
        raise TrialDownloadError("ClinicalTrials.gov returned an invalid NCT identifier.")
    eligibility = _module(protocol, "eligibilityModule")
    criteria = eligibility.get("eligibilityCriteria")
    status = _module(protocol, "statusModule")
    if not isinstance(criteria, str) or not criteria.strip():
        LOGGER.warning("Skipped %s: full eligibility text is missing", nct_id)
        return None
    if status.get("overallStatus") != "RECRUITING":
        LOGGER.warning("Skipped %s: recruitment status is not RECRUITING", nct_id)
        return None
    return {
        "nct_id": nct_id,
        "title": identity.get("briefTitle") or identity.get("officialTitle"),
        "overall_status": status.get("overallStatus"),
        "conditions": _module(protocol, "conditionsModule").get("conditions") or [],
        "brief_summary": _module(protocol, "descriptionModule").get("briefSummary"),
        "eligibility_criteria": criteria,
        "minimum_age": eligibility.get("minimumAge"),
        "maximum_age": eligibility.get("maximumAge"),
        "sex": eligibility.get("sex"),
        "locations": _module(protocol, "contactsLocationsModule").get("locations") or [],
        "interventions": _module(protocol, "armsInterventionsModule").get("interventions") or [],
        "source_url": f"https://clinicaltrials.gov/study/{nct_id}",
        "last_updated": (status.get("lastUpdatePostDateStruct") or {}).get("date")
        or status.get("lastUpdateSubmitDate"),
        "snapshot_date": snapshot_date,
    }


def iter_studies(session: requests.Session, query_params: dict, page_size: int = 100) -> Iterator[dict]:
    """Follow nextPageToken while preserving the same query and filters."""
    params = {
        **query_params, "filter.overallStatus": "RECRUITING", "format": "json",
        "pageSize": page_size, "countTotal": "true",
    }
    seen_tokens = set()
    while True:
        try:
            response = session.get(CLINICAL_TRIALS_API_URL, params=dict(params), timeout=30)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            raise TrialDownloadError("Cannot download ClinicalTrials.gov studies. Check the connection or retry later.") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("studies"), list):
            raise TrialDownloadError("ClinicalTrials.gov returned an invalid studies response.")
        for study in payload["studies"]:
            if not isinstance(study, dict):
                raise TrialDownloadError("ClinicalTrials.gov returned an invalid study record.")
            yield study
        token = payload.get("nextPageToken")
        if not token:
            break
        if not isinstance(token, str) or token in seen_tokens:
            raise TrialDownloadError("ClinicalTrials.gov returned an invalid or repeated pagination token.")
        seen_tokens.add(token)
        params["pageToken"] = token


def _matches_selection(record: dict, query: dict) -> bool:
    selection = query.get("selection_filter")
    if selection == "exclude_colorectal_conditions":
        conditions = " ".join(record["conditions"])
        return re.search(r"\b(colorectal|colon|rectal)\b", conditions, re.I) is None
    if selection == "g12d_without_g12c":
        text = " ".join(filter(None, [
            record["title"], record["brief_summary"], record["eligibility_criteria"],
            " ".join(record["conditions"]),
        ]))
        return bool(re.search(r"\bg12d\b", text, re.I)) and not re.search(r"\bg12c\b", text, re.I)
    if selection is not None:
        raise TrialDownloadError(f"Unknown selection filter for query '{query['name']}'.")
    return True


def collect_snapshot(
    session: requests.Session,
    snapshot_date: str,
    *,
    queries: tuple = TRIAL_QUERIES,
    page_size: int = 100,
    minimum_records: int = TRIAL_SNAPSHOT_MIN_RECORDS,
    maximum_records: int = TRIAL_SNAPSHOT_MAX_RECORDS,
) -> tuple[list[dict], dict]:
    date.fromisoformat(snapshot_date)
    if not 1 <= page_size <= 100:
        raise TrialDownloadError("page_size must be between 1 and 100.")
    records = {}
    query_stats = []
    for query in queries:
        added = skipped = 0
        for study in iter_studies(session, query["params"], page_size):
            record = normalize_study(study, snapshot_date)
            if record is None or not _matches_selection(record, query):
                skipped += 1
                continue
            nct_id = record["nct_id"]
            if nct_id in records:
                if query["name"] not in records[nct_id]["matched_queries"]:
                    records[nct_id]["matched_queries"].append(query["name"])
                continue
            record["selection_role"] = query["role"]
            record["matched_queries"] = [query["name"]]
            records[nct_id] = record
            added += 1
            if added >= query["limit"] or len(records) >= maximum_records:
                break
        query_stats.append({
            "name": query["name"], "role": query["role"], "params": query["params"],
            "requested_unique_records": query["limit"], "added_unique_records": added,
            "skipped_records": skipped, "selection_filter": query.get("selection_filter"),
        })
        LOGGER.info("%s: added %d unique records", query["name"], added)
        if len(records) >= maximum_records:
            break
    if not minimum_records <= len(records) <= maximum_records:
        raise TrialDownloadError(
            f"Downloaded {len(records)} unique records; expected {minimum_records}–{maximum_records}. "
            "No snapshot was written. Review the queries or retry later."
        )
    ordered_records = sorted(records.values(), key=lambda record: record["nct_id"])
    manifest = {
        "source": "ClinicalTrials.gov", "api_url": CLINICAL_TRIALS_API_URL,
        "snapshot_date": snapshot_date, "snapshot_timezone": "America/New_York",
        "record_count": len(ordered_records),
        "role_counts": dict(Counter(record["selection_role"] for record in ordered_records)),
        "query_results": query_stats,
        "eligibility_text_path": "protocolSection.eligibilityModule.eligibilityCriteria",
        "selection_note": "Query roles are corpus selection metadata, not gold relevance labels or patient assessments.",
        "runtime_note": "The application reads this frozen snapshot; no runtime ClinicalTrials.gov requests.",
    }
    return ordered_records, manifest


def write_snapshot(records: list[dict], manifest: dict, output_dir: Path, *, overwrite: bool = False) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    trials_path = output_dir / "trials.jsonl"
    manifest_path = output_dir / "snapshot_manifest.json"
    if not overwrite and (trials_path.exists() or manifest_path.exists()):
        raise TrialDownloadError("A frozen snapshot already exists. Use --overwrite only to deliberately refresh it.")
    trial_text = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    # Stage complete files before replacing their final paths.
    for path, text in [(trials_path, trial_text), (manifest_path, manifest_text)]:
        staged = path.with_suffix(path.suffix + ".tmp")
        staged.write_text(text, encoding="utf-8")
    trials_path.with_suffix(".jsonl.tmp").replace(trials_path)
    manifest_path.with_suffix(".json.tmp").replace(manifest_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-date", default=datetime.now(ZoneInfo("America/New_York")).date().isoformat())
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--overwrite", action="store_true", help="Deliberately replace the frozen snapshot")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        if not args.overwrite and any(
            (DEFAULT_OUTPUT_DIR / filename).exists() for filename in ["trials.jsonl", "snapshot_manifest.json"]
        ):
            raise TrialDownloadError("A frozen snapshot already exists. Use --overwrite to deliberately refresh it.")
        with requests.Session() as session:
            session.headers.update({"Accept": "application/json", "User-Agent": "TrialMatch-AI-prototype/0.1"})
            retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"], respect_retry_after_header=False)
            session.mount("https://", HTTPAdapter(max_retries=retry))
            records, manifest = collect_snapshot(session, args.snapshot_date, page_size=args.page_size)
        write_snapshot(records, manifest, DEFAULT_OUTPUT_DIR, overwrite=args.overwrite)
    except (TrialDownloadError, OSError, ValueError) as error:
        LOGGER.error("%s", error)
        raise SystemExit(1) from None
    LOGGER.info("Saved %d trial records to %s", len(records), DEFAULT_OUTPUT_DIR / "trials.jsonl")


if __name__ == "__main__":
    main()
