"""Load and normalize meetings from ICS feeds (Google secret address,
Outlook published calendar, or exported .ics files)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import icalendar
import recurring_ical_events
import requests

from .models import Meeting

FETCH_TIMEOUT_S = 30


def load_ics(source: str) -> bytes:
    """Read an ICS source: an http(s) URL or a local file path."""
    if source.startswith(("http://", "https://")):
        # Outlook publishes webcal-style links over https; Google secret
        # addresses are plain https as well.
        resp = requests.get(source, timeout=FETCH_TIMEOUT_S)
        resp.raise_for_status()
        return resp.content
    return Path(source).expanduser().read_bytes()


def _emails(event, my_emails: set[str]) -> frozenset[str]:
    raw = event.get("ATTENDEE", [])
    attendees = raw if isinstance(raw, list) else [raw]
    organizer = event.get("ORGANIZER")
    if organizer is not None:
        attendees = [*attendees, organizer]
    emails = {
        str(a).removeprefix("mailto:").removeprefix("MAILTO:").lower().strip()
        for a in attendees
    }
    return frozenset(e for e in emails if "@" in e and e not in my_emails)


def parse_meetings(
    feeds: list[bytes],
    window_start: datetime,
    window_end: datetime,
    *,
    my_emails: set[str],
) -> list[Meeting]:
    """Expand all feeds into concrete meetings within the window, deduped.

    All-day events (DATE-valued starts) are skipped — they say nothing about
    a specific block of heart-rate data.
    """
    meetings: dict[tuple, Meeting] = {}
    seen_summary_start: set[tuple] = set()
    for feed in feeds:
        cal = icalendar.Calendar.from_ical(feed)
        for event in recurring_ical_events.of(cal).between(window_start, window_end):
            start = event.get("DTSTART").dt
            end = event.get("DTEND").dt
            if not isinstance(start, datetime) or not isinstance(end, datetime):
                continue  # all-day event (DATE-valued)
            meeting = Meeting(
                uid=str(event.get("UID", "")),
                summary=str(event.get("SUMMARY", "")).strip(),
                start=start.timestamp(),
                end=end.timestamp(),
                attendees=_emails(event, my_emails),
            )
            fuzzy_key = (meeting.summary.lower(), meeting.start)
            if (meeting.uid, meeting.start) in meetings or fuzzy_key in seen_summary_start:
                continue
            meetings[(meeting.uid, meeting.start)] = meeting
            seen_summary_start.add(fuzzy_key)
    return sorted(meetings.values(), key=lambda m: m.start)
