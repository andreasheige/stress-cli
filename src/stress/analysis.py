"""Turn raw HR samples + meetings into per-meeting and per-person stress stats.

The approach mirrors the original idea: score each meeting's mean heart rate
against a local baseline (surrounding non-meeting time), then fit a ridge
regression over attendee presence so that the marginal effect of each person
is separated from co-attendance confounding.
"""

from __future__ import annotations

from collections import Counter
from statistics import mean, pstdev

import numpy as np

from .models import Meeting, MeetingStat

BASELINE_PAD_S = 90 * 60
MIN_MEETING_SAMPLES = 3
MIN_BASELINE_SAMPLES = 5
DEFAULT_LAMBDA = 1.0
DEFAULT_MIN_MEETINGS = 3

Sample = tuple[float, float]  # (epoch seconds, heart rate)


def _in_any_meeting(ts: float, meetings: list[Meeting]) -> bool:
    return any(m.start <= ts < m.end for m in meetings)


def compute_stats(
    meetings: list[Meeting],
    samples: list[Sample],
    *,
    baseline_pad: float = BASELINE_PAD_S,
    min_meeting_samples: int = MIN_MEETING_SAMPLES,
    min_baseline_samples: int = MIN_BASELINE_SAMPLES,
    extra_busy: list[Meeting] = (),
) -> list[MeetingStat]:
    """Score each meeting's mean HR against its surrounding non-meeting baseline.

    `extra_busy` intervals are excluded from baselines without being scored —
    e.g. real meetings while scoring message events.
    """
    busy = [*meetings, *extra_busy]
    stats = []
    for m in meetings:
        inside = [hr for ts, hr in samples if m.start <= ts < m.end]
        baseline = [
            hr
            for ts, hr in samples
            if (m.start - baseline_pad <= ts < m.start or m.end <= ts < m.end + baseline_pad)
            and not _in_any_meeting(ts, busy)
        ]
        if len(inside) < min_meeting_samples or len(baseline) < min_baseline_samples:
            continue
        stats.append(
            MeetingStat(
                meeting=m,
                mean_hr=mean(inside),
                baseline_hr=mean(baseline),
                n_samples=len(inside),
                baseline_std=pstdev(baseline),
            )
        )
    return stats


def _eligible_persons(stats: list[MeetingStat], min_meetings: int) -> list[str]:
    counts = Counter(p for s in stats for p in s.meeting.attendees)
    return sorted(p for p, n in counts.items() if n >= min_meetings)


def naive_scores(
    stats: list[MeetingStat], *, min_meetings: int = DEFAULT_MIN_MEETINGS
) -> dict[str, tuple[float, int]]:
    """Per person: (mean HR elevation across their meetings, meeting count)."""
    scores = {}
    for person in _eligible_persons(stats, min_meetings):
        elevations = [s.elevation for s in stats if person in s.meeting.attendees]
        scores[person] = (mean(elevations), len(elevations))
    return scores


def ridge_scores(
    stats: list[MeetingStat],
    *,
    lam: float = DEFAULT_LAMBDA,
    min_meetings: int = DEFAULT_MIN_MEETINGS,
) -> dict[str, float]:
    """Marginal HR-elevation effect per person via ridge regression.

    Rows are meetings, columns are attendees (presence indicator), target is
    the meeting's HR elevation. Regularization keeps the small, collinear
    design matrix (people who always meet together) from blowing up.
    """
    persons = _eligible_persons(stats, min_meetings)
    if not persons:
        return {}
    X = np.array(
        [[1.0 if p in s.meeting.attendees else 0.0 for p in persons] for s in stats]
    )
    y = np.array([s.elevation for s in stats])
    beta = np.linalg.solve(X.T @ X + lam * np.eye(len(persons)), X.T @ y)
    return dict(zip(persons, beta.tolist()))
