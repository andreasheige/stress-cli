"""Import heart rate from FIT and TCX workout files.

This is the universal escape hatch for watches without a usable API:
Suunto (app export), Polar (Flow export), and most others can export
recorded activities as .fit or .tcx. Note these files only contain HR
during recorded activities, not all-day wear.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Iterable
from xml.etree.ElementTree import fromstring

import fitdecode

from ..hrcache import SampleMs

TCX_NS = "{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}"


def parse_tcx(data: bytes) -> list[SampleMs]:
    samples = []
    root = fromstring(data)
    for point in root.iter(f"{TCX_NS}Trackpoint"):
        time_el = point.find(f"{TCX_NS}Time")
        hr_el = point.find(f"{TCX_NS}HeartRateBpm/{TCX_NS}Value")
        if time_el is None or hr_el is None:
            continue
        when = datetime.fromisoformat(time_el.text.strip())
        samples.append((when.timestamp() * 1000, float(hr_el.text)))
    return samples


def parse_fit_records(frames: Iterable) -> list[SampleMs]:
    """Extract (epoch_ms, bpm) from FIT data frames named 'record'."""
    samples = []
    for frame in frames:
        if (
            frame.frame_type == fitdecode.FIT_FRAME_DATA
            and frame.name == "record"
            and frame.has_field("timestamp")
            and frame.has_field("heart_rate")
        ):
            when = frame.get_value("timestamp")
            hr = frame.get_value("heart_rate")
            if hr is not None:
                samples.append((when.timestamp() * 1000, float(hr)))
    return samples


def import_file(path: Path) -> list[SampleMs]:
    if path.suffix.lower() == ".tcx":
        return parse_tcx(path.read_bytes())
    with fitdecode.FitReader(BytesIO(path.read_bytes())) as reader:
        return parse_fit_records(reader)
