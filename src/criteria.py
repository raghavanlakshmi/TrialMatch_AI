"""Deterministic parsing and loading of frozen trial eligibility criteria."""

from __future__ import annotations

import json
from pathlib import Path
import re

from pydantic import ValidationError

from .schemas import TrialCriterion, TrialRecord


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CRITERIA_PATH = PROJECT_ROOT / "data" / "trials" / "criteria.json"
_HEADING = re.compile(r"^\s*\*{0,2}\s*(inclusion|exclusion)(?:\s+criteria)?\s*:?\s*\*{0,2}\s*$", re.I)
_BULLET = re.compile(r"^\s*(?:[-*•]+|\d+[.)]|[a-z][.)])\s+(.*)$", re.I)


class CriteriaError(ValueError):
    pass


def _clean(text: str) -> str:
    return " ".join(text.replace("\\>=", ">=").replace("\\<=", "<=").split()).strip(" -*")


def parse_criteria(text: str) -> list[TrialCriterion]:
    """Split the demo corpus into stable inclusion/exclusion items.

    ClinicalTrials.gov formatting varies. Headings select the section, bullets
    start items, and wrapped lines remain attached to their preceding item.
    """
    section = "inclusion"
    blocks: dict[str, list[str]] = {"inclusion": [], "exclusion": []}
    current = ""

    def flush() -> None:
        nonlocal current
        cleaned = _clean(current)
        if cleaned and cleaned.casefold() not in {"none", "n/a", "not applicable"}:
            blocks[section].append(cleaned)
        current = ""

    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            flush()
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            section = heading.group(1).casefold()
            continue
        # Also accept headings followed by content on the same line.
        inline = re.match(r"^\s*\*{0,2}\s*(inclusion|exclusion)(?:\s+criteria)?\s*:\s*(.+)$", line, re.I)
        if inline:
            flush()
            section = inline.group(1).casefold()
            line = inline.group(2)
        bullet = _BULLET.match(line)
        if bullet:
            flush()
            current = bullet.group(1)
        elif current:
            current += " " + line
        else:
            current = line
    flush()

    criteria: list[TrialCriterion] = []
    for kind, prefix in (("inclusion", "INC"), ("exclusion", "EXC")):
        for number, item in enumerate(blocks[kind], start=1):
            criteria.append(TrialCriterion(
                criterion_id=f"{prefix}-{number:02d}", type=kind, text=item
            ))
    return criteria


def parse_trial_criteria(trials: list[TrialRecord]) -> dict[str, list[TrialCriterion]]:
    parsed = {trial.nct_id: parse_criteria(trial.eligibility_criteria) for trial in trials}
    empty = [nct_id for nct_id, items in parsed.items() if not items]
    if empty:
        raise CriteriaError(f"No criteria parsed for: {', '.join(empty)}")
    return parsed


def write_criteria(trials: list[TrialRecord], path: Path = DEFAULT_CRITERIA_PATH) -> None:
    parsed = parse_trial_criteria(trials)
    payload = {
        "snapshot_date": trials[0].snapshot_date,
        "parser_version": 1,
        "trials": {
            nct_id: [item.model_dump() for item in items]
            for nct_id, items in sorted(parsed.items())
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_criteria(path: Path = DEFAULT_CRITERIA_PATH) -> dict[str, list[TrialCriterion]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_trials = payload["trials"]
        if not isinstance(raw_trials, dict):
            raise TypeError
        return {
            nct_id: [TrialCriterion.model_validate(item) for item in items]
            for nct_id, items in raw_trials.items()
        }
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ValidationError):
        raise CriteriaError(f"Cannot load validated criteria from '{path}'.") from None
