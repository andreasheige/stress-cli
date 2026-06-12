"""Parsers for imported HR files: Apple Health export, TCX, FIT."""

from datetime import datetime, timezone

from stress.providers.apple_health import parse_health_xml
from stress.providers.workout_files import parse_fit_records, parse_tcx

HEALTH_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_SE">
 <Record type="HKQuantityTypeIdentifierHeartRate" unit="count/min" value="72"
         startDate="2026-06-01 09:00:00 +0200" endDate="2026-06-01 09:00:00 +0200"/>
 <Record type="HKQuantityTypeIdentifierHeartRate" unit="count/min" value="88.5"
         startDate="2026-06-01 09:05:00 +0200" endDate="2026-06-01 09:05:00 +0200"/>
 <Record type="HKQuantityTypeIdentifierStepCount" unit="count" value="500"
         startDate="2026-06-01 09:00:00 +0200" endDate="2026-06-01 09:10:00 +0200"/>
</HealthData>
"""

TCX = b"""<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
 <Activities><Activity Sport="Running"><Lap><Track>
  <Trackpoint>
   <Time>2026-06-01T07:00:00Z</Time>
   <HeartRateBpm><Value>95</Value></HeartRateBpm>
  </Trackpoint>
  <Trackpoint>
   <Time>2026-06-01T07:00:10Z</Time>
   <HeartRateBpm><Value>97</Value></HeartRateBpm>
  </Trackpoint>
  <Trackpoint>
   <Time>2026-06-01T07:00:20Z</Time>
  </Trackpoint>
 </Track></Lap></Activity></Activities>
</TrainingCenterDatabase>
"""


def test_parse_health_xml_extracts_hr_records_only():
    samples = parse_health_xml(HEALTH_XML)

    expected_ts = datetime(2026, 6, 1, 7, 0, tzinfo=timezone.utc).timestamp() * 1000
    assert samples == [(expected_ts, 72.0), (expected_ts + 300_000, 88.5)]


def test_parse_tcx_skips_trackpoints_without_hr():
    samples = parse_tcx(TCX)

    ts0 = datetime(2026, 6, 1, 7, 0, tzinfo=timezone.utc).timestamp() * 1000
    assert samples == [(ts0, 95.0), (ts0 + 10_000, 97.0)]


class FakeField:
    def __init__(self, name, value):
        self.name, self.value = name, value


class FakeFrame:
    frame_type = 4  # fitdecode.FIT_FRAME_DATA

    def __init__(self, name, fields):
        self.name = name
        self._fields = {f.name: f.value for f in fields}

    def has_field(self, name):
        return name in self._fields

    def get_value(self, name):
        return self._fields[name]


def test_parse_fit_records_reads_hr_from_record_frames():
    when = datetime(2026, 6, 1, 7, 0, tzinfo=timezone.utc)
    frames = [
        FakeFrame("record", [FakeField("timestamp", when), FakeField("heart_rate", 110)]),
        FakeFrame("record", [FakeField("timestamp", when)]),  # no HR -> skipped
        FakeFrame("session", [FakeField("timestamp", when)]),  # not a record
    ]

    assert parse_fit_records(frames) == [(when.timestamp() * 1000, 110.0)]
