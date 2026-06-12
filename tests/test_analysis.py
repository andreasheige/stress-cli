import math

from stress.analysis import compute_stats, naive_scores, ridge_scores
from stress.models import Meeting, MeetingStat

HOUR = 3600


def mk_meeting(start_h, end_h, attendees, uid="m", summary="meeting"):
    return Meeting(
        uid=uid,
        summary=summary,
        start=start_h * HOUR,
        end=end_h * HOUR,
        attendees=frozenset(attendees),
    )


def flat_samples(start_h, end_h, hr, step=120):
    """One sample every `step` seconds at a constant heart rate."""
    return [(ts, hr) for ts in range(int(start_h * HOUR), int(end_h * HOUR), step)]


class TestComputeStats:
    def test_elevation_vs_surrounding_baseline(self):
        # Baseline 60 bpm before and after, 80 bpm during the meeting.
        meeting = mk_meeting(10, 11, {"a@x.com"})
        samples = (
            flat_samples(9, 10, 60) + flat_samples(10, 11, 80) + flat_samples(11, 12, 60)
        )

        stats = compute_stats([meeting], samples)

        assert len(stats) == 1
        assert stats[0].mean_hr == 80
        assert stats[0].baseline_hr == 60
        assert stats[0].elevation == 20
        assert math.isclose(stats[0].rel_elevation, 20 / 60)

    def test_baseline_excludes_time_inside_other_meetings(self):
        # A stressful back-to-back meeting must not pollute the baseline.
        target = mk_meeting(10, 11, {"a@x.com"}, uid="t")
        adjacent = mk_meeting(11, 12, {"b@x.com"}, uid="adj")
        samples = (
            flat_samples(9, 10, 60)
            + flat_samples(10, 11, 80)
            + flat_samples(11, 12, 110)  # inside adjacent meeting -> excluded
        )

        stats = compute_stats([target, adjacent], samples)

        target_stat = next(s for s in stats if s.meeting.uid == "t")
        assert target_stat.baseline_hr == 60

    def test_skips_meetings_without_enough_samples(self):
        meeting = mk_meeting(10, 11, {"a@x.com"})
        samples = flat_samples(9, 10, 60) + [(int(10.5 * HOUR), 80)]  # 1 in-meeting sample

        assert compute_stats([meeting], samples) == []

    def test_skips_meetings_without_baseline_coverage(self):
        # HR data only exists during the meeting (e.g., watch off before/after).
        meeting = mk_meeting(10, 11, {"a@x.com"})
        samples = flat_samples(10, 11, 80)

        assert compute_stats([meeting], samples) == []


def mk_stat(attendees, elevation, uid="m"):
    meeting = mk_meeting(10, 11, attendees, uid=uid)
    return MeetingStat(meeting=meeting, mean_hr=60 + elevation, baseline_hr=60, n_samples=10)


class TestScores:
    def test_naive_scores_average_elevation_per_person(self):
        stats = [
            mk_stat({"a@x.com"}, 20, uid="1"),
            mk_stat({"a@x.com", "b@x.com"}, 10, uid="2"),
            mk_stat({"b@x.com"}, 0, uid="3"),
        ]

        scores = naive_scores(stats, min_meetings=1)

        assert scores["a@x.com"] == (15, 2)
        assert scores["b@x.com"] == (5, 2)

    def test_naive_scores_respects_min_meetings(self):
        stats = [mk_stat({"a@x.com"}, 20, uid="1"), mk_stat({"a@x.com"}, 10, uid="2")]

        scores = naive_scores(stats, min_meetings=3)

        assert scores == {}

    def test_ridge_attributes_stress_to_the_true_source(self):
        # b@x.com only ever appears alongside a@x.com, and meetings with a
        # are stressful while b's solo meetings are calm. Ridge should put
        # the blame on a, not split it evenly.
        stats = [
            mk_stat({"a@x.com", "b@x.com"}, 20, uid="1"),
            mk_stat({"a@x.com", "b@x.com"}, 22, uid="2"),
            mk_stat({"a@x.com", "c@x.com"}, 21, uid="3"),
            mk_stat({"b@x.com"}, 1, uid="4"),
            mk_stat({"b@x.com"}, -1, uid="5"),
            mk_stat({"c@x.com"}, 0, uid="6"),
            mk_stat({"c@x.com"}, 2, uid="7"),
        ]

        scores = ridge_scores(stats, lam=0.5, min_meetings=2)

        assert scores["a@x.com"] > scores["b@x.com"] + 10
        assert scores["a@x.com"] > scores["c@x.com"] + 10

    def test_ridge_empty_when_no_one_clears_min_meetings(self):
        stats = [mk_stat({"a@x.com"}, 20, uid="1")]

        assert ridge_scores(stats, min_meetings=3) == {}
