from datetime import date, timedelta

from stress import hrcache


def test_merge_day_dedupes_by_timestamp_and_sorts(tmp_path):
    day = date.today()

    hrcache.merge_day(tmp_path, day, [(2000, 70.0), (1000, 65.0)])
    hrcache.merge_day(tmp_path, day, [(2000, 71.0), (3000, 80.0)])

    samples = hrcache.load_samples(tmp_path, days=1)
    # Later import wins on timestamp collision; output sorted, ms -> s.
    assert samples == [(1.0, 65.0), (2.0, 71.0), (3.0, 80.0)]


def test_load_samples_respects_day_window(tmp_path):
    today = date.today()
    hrcache.merge_day(tmp_path, today, [(1000, 60.0)])
    hrcache.merge_day(tmp_path, today - timedelta(days=5), [(2000, 90.0)])

    assert hrcache.load_samples(tmp_path, days=2) == [(1.0, 60.0)]
    assert len(hrcache.load_samples(tmp_path, days=10)) == 2


def test_load_samples_skips_null_hr(tmp_path):
    day = date.today()
    (tmp_path / f"{day.isoformat()}.json").write_text("[[1000, null], [2000, 70]]")

    assert hrcache.load_samples(tmp_path, days=1) == [(2.0, 70.0)]
