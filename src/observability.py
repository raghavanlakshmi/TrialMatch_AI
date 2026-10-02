"""Small in-process trace for workflow observability."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from time import perf_counter
from typing import Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def trace_step(trace: list[dict], step: str, *, input_count: int = 0, model: str | None = None) -> Iterator[dict]:
    started_at = utc_now()
    start = perf_counter()
    record = {"step": step, "started_at": started_at, "input_count": input_count, "status": "success", "llm_calls": 0}
    if model:
        record["model"] = model
    try:
        yield record
    except Exception as error:
        record["status"] = "error"
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        record["ended_at"] = utc_now()
        record["latency_ms"] = round((perf_counter() - start) * 1000, 2)
        record.setdefault("output_count", 0)
        trace.append(record)
