"""Load config.toml: calendar sources, own email addresses, analysis knobs."""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .analysis import DEFAULT_LAMBDA, DEFAULT_MIN_MEETINGS

CONFIG_PATH = Path("config.toml")


@dataclass(frozen=True)
class Config:
    calendars: list[str]
    my_emails: set[str]
    provider: str = "garmin"
    lam: float = DEFAULT_LAMBDA
    min_meetings: int = DEFAULT_MIN_MEETINGS
    data_dir: Path = field(default_factory=lambda: Path("data"))


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        sys.exit(
            f"No {path} found. Copy config.example.toml to {path} and fill in "
            "your calendar ICS URLs and email addresses."
        )
    raw = tomllib.loads(path.read_text())
    calendars = raw.get("calendars", [])
    if not calendars:
        sys.exit(f"{path} has no calendars — add at least one ICS URL or file path.")
    analysis = raw.get("analysis", {})
    return Config(
        calendars=calendars,
        my_emails={e.lower() for e in raw.get("me", [])},
        provider=raw.get("provider", "garmin"),
        lam=float(analysis.get("lambda", DEFAULT_LAMBDA)),
        min_meetings=int(analysis.get("min_meetings", DEFAULT_MIN_MEETINGS)),
    )
