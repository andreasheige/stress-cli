"""Render per-meeting stats and the per-person leaderboard in the terminal."""

from __future__ import annotations

from datetime import datetime

from .analysis import naive_scores, ridge_scores
from .models import MeetingStat

BAR_CHAR = "█"
BAR_MAX_WIDTH = 14

VERDICTS = [
    (5.0, "prime suspect"),
    (2.0, "raises HR"),
    (0.5, "slightly raises HR"),
    (-0.5, "neutral"),
    (-2.0, "mild relief"),
    (float("-inf"), "calming"),
]


def _verdict(score: float) -> str:
    return next(label for threshold, label in VERDICTS if score >= threshold)


def _bar(value: float, scale_max: float) -> str:
    if scale_max <= 0:
        return ""
    width = round(abs(value) / scale_max * BAR_MAX_WIDTH)
    return BAR_CHAR * max(width, 1) if abs(value) > 0.05 else ""


def _short(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def render(stats: list[MeetingStat], *, lam: float, min_meetings: int, top: int) -> str:
    lines = []
    out = lines.append

    out("TOP MEETINGS BY HR ELEVATION")
    out(f"  {'Δbpm':>6}  {'rel':>4}  {'when':<15} {'meeting':<32} attendees")
    ranked = sorted(stats, key=lambda s: s.elevation, reverse=True)[:top]
    max_elev = max((abs(s.elevation) for s in ranked), default=0)
    for s in ranked:
        when = datetime.fromtimestamp(s.meeting.start).strftime("%a %m-%d %H:%M")
        people = ", ".join(sorted(a.split("@")[0] for a in s.meeting.attendees))
        out(
            f"  {s.elevation:+6.1f}  {s.rel_elevation:+4.0%}  {when:<15} "
            f"{_short(s.meeting.summary, 32):<32} {_bar(s.elevation, max_elev):<{BAR_MAX_WIDTH}} "
            f"{_short(people, 40)}"
        )

    out("")
    out(f"LEADERBOARD — marginal HR effect per person (ridge λ={lam:g})")
    lines.extend(_leaderboard(stats, lam=lam, min_meetings=min_meetings, unit="meetings"))

    return "\n".join(lines)


def render_messages(stats: list[MeetingStat], *, lam: float, min_meetings: int) -> str:
    lines = [
        "SLACK — HR effect in the minutes after someone messages you (outside meetings)",
        f"  scored {len(stats)} message event(s)",
    ]
    lines.extend(_leaderboard(stats, lam=lam, min_meetings=min_meetings, unit="message events"))
    return "\n".join(lines)


def _leaderboard(
    stats: list[MeetingStat], *, lam: float, min_meetings: int, unit: str
) -> list[str]:
    lines = [f"  {'#':>2}  {'person':<34} {'ridge':>6}  {'naive':>6}  {'n':>3}"]
    ridge = ridge_scores(stats, lam=lam, min_meetings=min_meetings)
    naive = naive_scores(stats, min_meetings=min_meetings)
    board = sorted(ridge.items(), key=lambda kv: kv[1], reverse=True)
    max_ridge = max((abs(v) for _, v in board), default=0)
    for rank, (person, score) in enumerate(board, start=1):
        naive_mean, n = naive[person]
        lines.append(
            f"  {rank:>2}  {_short(person, 34):<34} {score:+6.2f}  {naive_mean:+6.2f}  {n:>3}"
            f"  {_bar(score, max_ridge):<{BAR_MAX_WIDTH}} {_verdict(score)}"
        )
    if not board:
        lines.append(f"  (no one has ≥{min_meetings} scored {unit} yet — try --min-meetings 1)")
    return lines
