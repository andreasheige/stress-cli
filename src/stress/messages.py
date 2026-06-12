"""Message events (Slack, later Teams): cache and conversion to pseudo-meetings.

A message directed at you is treated as a short stress event: the window
after it lands becomes a pseudo-meeting whose only "attendee" is the sender,
so the existing baseline + ridge pipeline scores senders like coworkers in
meetings. Messages arriving during real meetings are dropped (the meeting
would confound the sender), and windows are clipped at the next meeting.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from .analysis import _in_any_meeting
from .models import Meeting

MESSAGE_WINDOW_S = 10 * 60
MESSAGES_FILE = "messages.json"


@dataclass(frozen=True)
class Message:
    ts: float  # epoch seconds
    sender: str
    source: str


def merge_messages(data_dir: Path, new: list[Message]) -> int:
    """Merge messages into the cache, deduped by (ts, sender, source)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / MESSAGES_FILE
    by_key = {}
    if path.exists():
        for raw in json.loads(path.read_text()):
            m = Message(**raw)
            by_key[(m.ts, m.sender, m.source)] = m
    for m in new:
        by_key[(m.ts, m.sender, m.source)] = m
    merged = sorted(by_key.values(), key=lambda m: m.ts)
    path.write_text(json.dumps([asdict(m) for m in merged]))
    return len(merged)


def load_messages(data_dir: Path, days: int) -> list[Message]:
    path = data_dir / MESSAGES_FILE
    if not path.exists():
        return []
    oldest = time.time() - days * 86400
    messages = [Message(**raw) for raw in json.loads(path.read_text())]
    return [m for m in messages if m.ts >= oldest]


def to_events(
    messages: list[Message],
    meetings: list[Meeting],
    *,
    window_s: float = MESSAGE_WINDOW_S,
) -> list[Meeting]:
    """Convert messages into per-sender pseudo-meetings, merging bursts."""
    by_sender: dict[str, list[Message]] = defaultdict(list)
    for m in messages:
        if not _in_any_meeting(m.ts, meetings):
            by_sender[m.sender].append(m)

    events = []
    for sender, sender_msgs in by_sender.items():
        source = sender_msgs[0].source
        intervals: list[list[float]] = []
        for m in sorted(sender_msgs, key=lambda m: m.ts):
            if intervals and m.ts <= intervals[-1][1]:
                intervals[-1][1] = m.ts + window_s
            else:
                intervals.append([m.ts, m.ts + window_s])
        for start, end in intervals:
            end = min(
                (mt.start for mt in meetings if start < mt.start < end), default=end
            )
            events.append(
                Meeting(
                    uid=f"{source}-{sender}-{int(start)}",
                    summary=f"{source} messages from {sender}",
                    start=start,
                    end=end,
                    attendees=frozenset({sender}),
                )
            )
    return sorted(events, key=lambda e: e.start)
