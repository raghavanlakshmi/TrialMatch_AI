"""Load and normalize the frozen ClinicalTrials.gov trial snapshot."""

import argparse
from collections.abc import Iterable
import json
import logging
from pathlib import Path
import re

from pydantic import ValidationError

from .schemas import TrialRecord


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRIALS_PATH = PROJECT_ROOT / "data" / "trials" / "trials.jsonl"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "data" / "trials" / "snapshot_manifest.json"
DEFAULT_NORMALIZED_PATH = PROJECT_ROOT / "data" / "trials" / "normalized_trials.jsonl"
_AGE_PATTERN = re.compile(
    r"^\s*(?P<amount>\d+(?:\.\d+)?)\s+"
    r"(?P<unit>years?|months?|weeks?|days?|hours?|minutes?)\s*$",
    re.IGNORECASE,
)
_DAYS_PER_YEAR = 365.2425


class TrialLoadError(ValueError):
    """The frozen trial snapshot cannot be safely loaded."""


def parse_age_to_years(value: str | None) -> float | None:
    """Convert a ClinicalTrials.gov age string to years without guessing."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TrialLoadError("Age must be null or a value such as '18 Years' or '6 Months'.")
    match = _AGE_PATTERN.fullmatch(value)
    if match is None:
        raise TrialLoadError(f"Unsupported ClinicalTrials.gov age value: {value!r}.")
    amount = float(match.group("amount"))
    unit = match.group("unit").casefold().rstrip("s")
    if unit == "year":
        years = amount
    elif unit == "month":
        years = amount / 12
    elif unit == "week":
        years = amount * 7 / _DAYS_PER_YEAR
    elif unit == "day":
        years = amount / _DAYS_PER_YEAR
    elif unit == "hour":
        years = amount / (_DAYS_PER_YEAR * 24)
    else:
        years = amount / (_DAYS_PER_YEAR * 24 * 60)
    return round(years, 8)


def _validated_trial(raw_record: object, line_number: int) -> TrialRecord:
    if not isinstance(raw_record, dict):
        raise TrialLoadError(f"Trial JSONL line {line_number} must contain an object.")
    record = dict(raw_record)
    try:
        record["minimum_age_years"] = parse_age_to_years(record.get("minimum_age"))
        record["maximum_age_years"] = parse_age_to_years(record.get("maximum_age"))
        trial = TrialRecord.model_validate(record)
    except (TrialLoadError, ValidationError) as error:
        raise TrialLoadError(f"Invalid trial on JSONL line {line_number}: {error}") from None
    if trial.source_url != f"https://clinicaltrials.gov/study/{trial.nct_id}":
        raise TrialLoadError(
            f"Invalid trial on JSONL line {line_number}: source URL does not match {trial.nct_id}."
        )
    if (
        trial.minimum_age_years is not None
        and trial.maximum_age_years is not None
        and trial.minimum_age_years > trial.maximum_age_years
    ):
        raise TrialLoadError(
            f"Invalid trial on JSONL line {line_number}: minimum age exceeds maximum age."
        )
    return trial


def load_trials(
    path: str | Path = DEFAULT_TRIALS_PATH,
    *,
    manifest_path: str | Path | None = DEFAULT_MANIFEST_PATH,
) -> list[TrialRecord]:
    """Load JSONL, validate provenance, ages, uniqueness, and manifest metadata."""
    source_path = Path(path)
    try:
        lines = source_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        raise TrialLoadError(f"Cannot read frozen trial snapshot '{source_path}'.") from None
    trials = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw_record = json.loads(line)
        except json.JSONDecodeError as error:
            raise TrialLoadError(
                f"Invalid JSON on trial snapshot line {line_number}: {error.msg}."
            ) from None
        trials.append(_validated_trial(raw_record, line_number))
    if not trials:
        raise TrialLoadError("The frozen trial snapshot contains no trial records.")
    nct_ids = [trial.nct_id for trial in trials]
    if len(set(nct_ids)) != len(nct_ids):
        duplicate = next(nct_id for nct_id in nct_ids if nct_ids.count(nct_id) > 1)
        raise TrialLoadError(f"Duplicate trial identifier in snapshot: {duplicate}.")
    if manifest_path is not None:
        _validate_manifest(trials, Path(manifest_path))
    LOGGER.info("Loaded %d frozen trial records from %s", len(trials), source_path)
    return trials


def _validate_manifest(trials: list[TrialRecord], manifest_path: Path) -> None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError:
        raise TrialLoadError(f"Cannot read trial snapshot manifest '{manifest_path}'.") from None
    except json.JSONDecodeError:
        raise TrialLoadError("The trial snapshot manifest is not valid JSON.") from None
    if not isinstance(manifest, dict):
        raise TrialLoadError("The trial snapshot manifest must contain an object.")
    if manifest.get("record_count") != len(trials):
        raise TrialLoadError("Trial count does not match snapshot_manifest.json.")
    snapshot_date = manifest.get("snapshot_date")
    if not isinstance(snapshot_date, str) or any(
        trial.snapshot_date != snapshot_date for trial in trials
    ):
        raise TrialLoadError("Trial dates do not match snapshot_manifest.json.")
    role_counts = {
        role: sum(trial.selection_role == role for trial in trials)
        for role in ("candidate", "distractor")
    }
    if manifest.get("role_counts") != {role: count for role, count in role_counts.items() if count}:
        raise TrialLoadError("Trial role counts do not match snapshot_manifest.json.")


def build_searchable_text(trial: TrialRecord) -> str:
    """Create one stable, readable document without changing source criteria text."""
    conditions = "; ".join(trial.conditions)
    summary = trial.brief_summary.strip() if trial.brief_summary else "Not provided"
    return "\n".join(
        [
            f"NCT ID: {trial.nct_id}",
            f"Title: {trial.title.strip()}",
            f"Conditions: {conditions}",
            f"Status: {trial.overall_status}",
            f"Summary: {summary}",
            "Eligibility:",
            trial.eligibility_criteria.strip(),
        ]
    )


def normalized_trial_record(trial: TrialRecord) -> dict:
    """Return source fields, parsed ages, and normalized searchable text."""
    record = trial.model_dump()
    record["searchable_text"] = build_searchable_text(trial)
    return record


def write_normalized_trials(
    trials: Iterable[TrialRecord],
    path: str | Path = DEFAULT_NORMALIZED_PATH,
    *,
    overwrite: bool = False,
) -> None:
    """Write a deterministic derived JSONL file without altering the raw snapshot."""
    destination = Path(path)
    if destination.exists() and not overwrite:
        raise TrialLoadError(
            f"Normalized trial file already exists: '{destination}'. Use overwrite=True to replace it."
        )
    records = list(trials)
    if not records:
        raise TrialLoadError("Cannot write an empty normalized trial file.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with staged.open("w", encoding="utf-8", newline="\n") as output:
            for trial in records:
                output.write(json.dumps(normalized_trial_record(trial), ensure_ascii=False) + "\n")
        staged.replace(destination)
    except OSError:
        raise TrialLoadError(f"Cannot write normalized trial file '{destination}'.") from None
    LOGGER.info("Wrote %d normalized trial records to %s", len(records), destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_TRIALS_PATH)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_NORMALIZED_PATH)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        trials = load_trials(args.source, manifest_path=args.manifest)
        write_normalized_trials(trials, args.output, overwrite=args.overwrite)
    except TrialLoadError as error:
        LOGGER.error("%s", error)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
