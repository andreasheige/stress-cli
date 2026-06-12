from datetime import datetime, timezone

from stress.calendars import parse_meetings

ICS_TEMPLATE = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//test//EN
{events}END:VCALENDAR
"""

SIMPLE_EVENT = """BEGIN:VEVENT
UID:event-1
SUMMARY:Weekly sync
DTSTART:20260601T090000Z
DTEND:20260601T100000Z
ORGANIZER:mailto:Boss@Example.com
ATTENDEE;CN=Me:mailto:me@example.com
ATTENDEE;CN=Colleague:mailto:colleague@example.com
END:VEVENT
"""

ALL_DAY_EVENT = """BEGIN:VEVENT
UID:event-2
SUMMARY:Public holiday
DTSTART;VALUE=DATE:20260601
DTEND;VALUE=DATE:20260602
END:VEVENT
"""

RECURRING_EVENT = """BEGIN:VEVENT
UID:event-3
SUMMARY:Daily standup
DTSTART:20260601T080000Z
DTEND:20260601T081500Z
RRULE:FREQ=DAILY;COUNT=5
ATTENDEE:mailto:colleague@example.com
END:VEVENT
"""

WINDOW = (
    datetime(2026, 6, 1, tzinfo=timezone.utc),
    datetime(2026, 6, 8, tzinfo=timezone.utc),
)


def ics(*events):
    return ICS_TEMPLATE.format(events="".join(events)).encode()


class TestParseMeetings:
    def test_extracts_times_and_attendees(self):
        meetings = parse_meetings([ics(SIMPLE_EVENT)], *WINDOW, my_emails={"me@example.com"})

        assert len(meetings) == 1
        m = meetings[0]
        assert m.summary == "Weekly sync"
        assert m.start == datetime(2026, 6, 1, 9, tzinfo=timezone.utc).timestamp()
        assert m.duration_min == 60
        # Organizer is included, emails lowercased, my own address removed.
        assert m.attendees == frozenset({"boss@example.com", "colleague@example.com"})

    def test_skips_all_day_events(self):
        meetings = parse_meetings([ics(ALL_DAY_EVENT)], *WINDOW, my_emails=set())

        assert meetings == []

    def test_expands_recurring_events_within_window(self):
        meetings = parse_meetings([ics(RECURRING_EVENT)], *WINDOW, my_emails=set())

        assert len(meetings) == 5
        assert len({m.start for m in meetings}) == 5

    def test_dedupes_same_event_across_calendars(self):
        # The same meeting synced into both Google and Outlook feeds.
        meetings = parse_meetings(
            [ics(SIMPLE_EVENT), ics(SIMPLE_EVENT)], *WINDOW, my_emails=set()
        )

        assert len(meetings) == 1

    def test_dedupes_by_summary_and_start_when_uids_differ(self):
        other_uid = SIMPLE_EVENT.replace("UID:event-1", "UID:outlook-99")
        meetings = parse_meetings(
            [ics(SIMPLE_EVENT), ics(other_uid)], *WINDOW, my_emails=set()
        )

        assert len(meetings) == 1
