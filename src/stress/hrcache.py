"""Provider-agnostic heart-rate day cache.

One JSON file per local calendar day: [[epoch_ms, bpm], ...]. Every provider
(Garmin API fetch, Apple Health import, FIT/TCX import) writes here, and the
report reads from here.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

SampleMs = tuple[float, float]  # (epoch milliseconds, bpm)


def day_path(cache_dir: Path, day: date) -> Path:
    return cache_dir / f"{day.isoformat()}.json"


def merge_day(cache_dir: Path, day: date, samples: list[SampleMs]) -> int:
    """Merge samples into a day's cache file, deduped by timestamp.

    On collision the new sample wins. Returns the day's total sample count.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = day_path(cache_dir, day)
    by_ts: dict[float, float] = {}
    if path.exists():
        for ts_ms, hr in json.loads(path.read_text()):
            if hr is not None:
                by_ts[ts_ms] = hr
    for ts_ms, hr in samples:
        if hr is not None:
            by_ts[ts_ms] = hr
    merged = sorted(by_ts.items())
    path.write_text(json.dumps(merged))
    return len(merged)


def merge_samples(cache_dir: Path, samples: list[SampleMs]) -> dict[date, int]:
    """Group samples by local calendar day and merge each into the cache."""
    by_day: dict[date, list[SampleMs]] = defaultdict(list)
    for ts_ms, hr in samples:
        by_day[datetime.fromtimestamp(ts_ms / 1000).date()].append((ts_ms, hr))
    return {day: merge_day(cache_dir, day, day_samples) for day, day_samples in by_day.items()}


def load_samples(cache_dir: Path, days: int) -> list[tuple[float, float]]:
    """Load cached samples for the last `days` days as (epoch seconds, bpm)."""
    samples = []
    today = date.today()
    for offset in range(days):
        path = day_path(cache_dir, today - timedelta(days=offset))
        if not path.exists():
            continue
        for ts_ms, hr in json.loads(path.read_text()):
            if hr is not None:
                samples.append((ts_ms / 1000, float(hr)))
    return sorted(samples)
