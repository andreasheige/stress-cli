"""Core data types shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Meeting:
    """A calendar event, normalized to epoch seconds and attendee emails."""

    uid: str
    summary: str
    start: float
    end: float
    attendees: frozenset[str]

    @property
    def duration_min(self) -> float:
        return (self.end - self.start) / 60


@dataclass(frozen=True)
class MeetingStat:
    """Heart-rate statistics for one meeting vs its local baseline."""

    meeting: Meeting
    mean_hr: float
    baseline_hr: float
    n_samples: int
    baseline_std: float = 0.0

    @property
    def elevation(self) -> float:
        return self.mean_hr - self.baseline_hr

    @property
    def rel_elevation(self) -> float:
        return self.elevation / self.baseline_hr

    @property
    def z(self) -> float:
        """Elevation in units of baseline variability."""
        return self.elevation / self.baseline_std if self.baseline_std > 1e-9 else 0.0
