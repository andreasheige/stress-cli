"""End-to-end: synthetic ICS + HR samples through parse -> stats -> report."""

from datetime import datetime, timezone

from stress.analysis import compute_stats
from stress.calendars import parse_meetings
from stress.report import Palette, render_board, render_meetings

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//test//EN
BEGIN:VEVENT
UID:standup
SUMMARY:Daily standup
DTSTART:20260601T080000Z
DTEND:20260601T083000Z
RRULE:FREQ=DAILY;COUNT=5
ATTENDEE:mailto:calm@x.com
END:VEVENT
BEGIN:VEVENT
UID:review
SUMMARY:Design review
DTSTART:20260601T130000Z
DTEND:20260601T140000Z
RRULE:FREQ=DAILY;COUNT=5
ATTENDEE:mailto:stressor@x.com
ATTENDEE:mailto:calm@x.com
END:VEVENT
END:VCALENDAR
""".encode()

WINDOW = (
    datetime(2026, 6, 1, tzinfo=timezone.utc),
    datetime(2026, 6, 7, tzinfo=timezone.utc),
)


def synthetic_samples(meetings):
    """Resting 62 bpm everywhere, 85 bpm inside any meeting with stressor@."""
    samples = []
    day_start = int(WINDOW[0].timestamp())
    for ts in range(day_start, int(WINDOW[1].timestamp()), 120):
        hr = 62.0
        for m in meetings:
            if m.start <= ts < m.end and "stressor@x.com" in m.attendees:
                hr = 85.0
        samples.append((float(ts), hr))
    return samples


def test_full_pipeline_blames_the_stressor():
    meetings = parse_meetings([ICS], *WINDOW, my_emails={"me@x.com"})
    assert len(meetings) == 10

    stats = compute_stats(meetings, synthetic_samples(meetings))
    assert len(stats) == 10

    pal = Palette(enabled=False)
    table = render_meetings(stats, top=5, pal=pal)
    assert "Design review" in table

    board = render_board(
        stats, title="PER-PERSON", subtitle="test", lam=1.0, min_meetings=3, pal=pal
    )
    rows = [l for l in board.splitlines() if l.strip().startswith(("stressor", "calm"))]
    assert rows[0].strip().startswith("stressor")
    assert rows[1].strip().startswith("calm")
    assert "prime suspect" in rows[0] or "raises HR" in rows[0]
