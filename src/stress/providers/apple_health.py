"""Import heart rate from an Apple Health export (export.zip or export.xml).

Apple Watch has no cloud API, but Health → profile → "Export All Health Data"
produces a zip whose export.xml contains every HR sample ever recorded.
The file is routinely hundreds of MB, so it is parsed with iterparse.
"""

from __future__ import annotations

import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import IO
from xml.etree.ElementTree import iterparse

from ..hrcache import SampleMs

HR_TYPE = "HKQuantityTypeIdentifierHeartRate"
APPLE_DATE_FORMAT = "%Y-%m-%d %H:%M:%S %z"


def _parse_stream(stream: IO[bytes]) -> list[SampleMs]:
    samples = []
    for _, elem in iterparse(stream, events=("end",)):
        if elem.tag == "Record" and elem.get("type") == HR_TYPE:
            when = datetime.strptime(elem.get("startDate"), APPLE_DATE_FORMAT)
            samples.append((when.timestamp() * 1000, float(elem.get("value"))))
        elem.clear()  # keep memory flat on huge exports
    return samples


def parse_health_xml(data: bytes) -> list[SampleMs]:
    return _parse_stream(BytesIO(data))


def import_file(path: Path) -> list[SampleMs]:
    """Parse an Apple Health export.zip or a bare export.xml."""
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            xml_name = next(
                n for n in zf.namelist() if n.endswith("export.xml") and "cda" not in n
            )
            with zf.open(xml_name) as stream:
                return _parse_stream(stream)
    with path.open("rb") as stream:
        return _parse_stream(stream)
