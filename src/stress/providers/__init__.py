"""HR data providers.

Two kinds of sources feed the shared day cache (see hrcache):
- API providers, used by `stress fetch` (registered in FETCHERS)
- file importers, used by `stress import` (dispatched by extension)
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..hrcache import SampleMs
from . import apple_health, garmin, workout_files

# provider name -> fetch_days(days, cache_dir) -> days fetched
FETCHERS: dict[str, Callable[[int, Path], int]] = {
    "garmin": garmin.fetch_days,
}

_IMPORTERS: dict[str, Callable[[Path], list[SampleMs]]] = {
    ".zip": apple_health.import_file,
    ".xml": apple_health.import_file,
    ".fit": workout_files.import_file,
    ".tcx": workout_files.import_file,
}


def import_file(path: Path) -> list[SampleMs]:
    """Parse any supported export file into HR samples."""
    importer = _IMPORTERS.get(path.suffix.lower())
    if importer is None:
        supported = ", ".join(sorted(_IMPORTERS))
        raise ValueError(f"Unsupported file type '{path.suffix}' (supported: {supported})")
    return importer(path)
