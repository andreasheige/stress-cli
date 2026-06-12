"""ANSI-colored terminal report styled after the original whoops screenshot:
wear summary, pipeline log lines, meeting stress table, per-person boards
with diverging calming↔stress bars, and CSV export."""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from statistics import median

from .analysis import naive_scores, ridge_scores
from .models import MeetingStat

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RED = "\x1b[38;5;203m"
GREEN = "\x1b[38;5;114m"
YELLOW = "\x1b[38;5;179m"
CYAN = "\x1b[38;5;110m"
GREY = "\x1b[38;5;246m"

BAR = "█"
DIV_BAR = "▆"
MEETING_BAR_W = 9
DIV_BAR_W = 7
PARTIAL_WEAR_FRACTION = 0.6
INTRO_DAYS_SHOWN = 4

VERDICTS = [
    (5.0, "prime suspect", RED + BOLD),
    (2.0, "raises HR", RED),
    (0.5, "slightly raises HR", YELLOW),
    (-0.5, "neutral", GREY),
    (-2.0, "mild relief", GREEN),
    (float("-inf"), "calming", GREEN),
]


class Palette:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def paint(self, text: str, *codes: str) -> str:
        if not self.enabled or not codes or not text:
            return text
        return f"{''.join(codes)}{text}{RESET}"

    def signed(self, text: str, value: float, threshold: float = 0.05) -> str:
        if value > threshold:
            return self.paint(text, RED)
        if value < -threshold:
            return self.paint(text, GREEN)
        return self.paint(text, GREY)


def _verdict(score: float) -> tuple[str, str]:
    return next((label, code) for t, label, code in VERDICTS if score >= t)


def _bar_width(value: float, scale_max: float, max_width: int) -> int:
    """At least one cell for anything non-negligible, so small effects stay visible."""
    if scale_max <= 0 or abs(value) <= 0.05:
        return 0
    return max(1, round(abs(value) / scale_max * max_width))


def _short(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _names(attendees: frozenset[str]) -> str:
    return ", ".join(sorted(a.split("@")[0] for a in attendees))


def _reliability(n: int) -> str:
    if n >= 8:
        return "high"
    if n >= 4:
        return "med"
    return "low"


def render_intro(
    day_counts: list[tuple[date, int]],
    *,
    days: int,
    n_meetings: int,
    n_attendees: int,
    n_busy: int,
    n_messages: int,
    lam: float,
    pal: Palette,
) -> str:
    lines = []
    worn = [n for _, n in day_counts if n > 0]
    typical = median(worn) if worn else 0
    for day, n in day_counts[-INTRO_DAYS_SHOWN:]:
        label = pal.paint(day.strftime("%a %Y-%m-%d"), GREY)
        pts = f"{n:>6,} pts" if n else pal.paint("     no data", GREY)
        note = ""
        if 0 < n < PARTIAL_WEAR_FRACTION * typical:
            note = "   " + pal.paint("partial wear", YELLOW)
        lines.append(f"  {label}  {pts}{note}")
    total = sum(n for _, n in day_counts)
    tag = pal.paint("[stress]", CYAN)
    lines.append(f"{tag} {total:,} HR points over {days} days")
    lines.append("")
    cal = pal.paint("[cal]", YELLOW)
    run = pal.paint("[run]", CYAN)
    lines.append(
        f"{cal}   {n_meetings} meetings, {n_attendees} attendees"
        f" (+{n_busy} busy blocks without attendee info)"
    )
    if n_messages:
        slack = pal.paint("[slack]", YELLOW)
        lines.append(f"{slack} {n_messages:,} DMs/mentions from the last {days} days")
    lines.append(f"{run}   scoring each meeting vs 90-min local baseline …")
    lines.append(f"{run}   fitting attendee model (ridge λ={lam:g}) …")
    return "\n".join(lines)


def render_meetings(stats: list[MeetingStat], *, top: int, pal: Palette) -> str:
    title = pal.paint("MEETING STRESS", BOLD)
    subtitle = pal.paint("mean HR over surrounding baseline", GREY)
    lines = [f"{title}   {subtitle}", ""]
    header = f"   {'Δbpm':>5}  {'z':>5}  {'elev':>5}  {'':{MEETING_BAR_W}} {'meeting':<26}  attendees"
    lines.append(pal.paint(header, GREY))
    ranked = sorted(stats, key=lambda s: s.elevation, reverse=True)[:top]
    max_elev = max((abs(s.elevation) for s in ranked), default=0)
    for s in ranked:
        width = _bar_width(s.elevation, max_elev, MEETING_BAR_W)
        bar = pal.signed(BAR * width, s.elevation) + " " * (MEETING_BAR_W - width)
        when = datetime.fromtimestamp(s.meeting.start).strftime("%m-%d %H:%M")
        name = _short(s.meeting.summary, 26)
        lines.append(
            f"   {pal.signed(f'{s.elevation:+5.1f}', s.elevation)}"
            f"  {s.z:+5.2f}"
            f"  {s.rel_elevation:+4.0%}"
            f"  {bar} {name:<26}"
            f"  {pal.paint(_short(f'{when}  {_names(s.meeting.attendees)}', 52), GREY)}"
        )
    return "\n".join(lines)


def render_board(
    stats: list[MeetingStat],
    *,
    title: str,
    subtitle: str,
    lam: float,
    min_meetings: int,
    pal: Palette,
) -> str:
    lines = [f"{pal.paint(title, BOLD)}   {pal.paint(subtitle, GREY)}", ""]
    ridge = ridge_scores(stats, lam=lam, min_meetings=min_meetings)
    naive = naive_scores(stats, min_meetings=min_meetings)
    board = sorted(ridge.items(), key=lambda kv: kv[1], reverse=True)
    if not board:
        lines.append(
            pal.paint(f"  (no one has ≥{min_meetings} scored events yet)", GREY)
        )
        return "\n".join(lines)

    header = (
        f"  {'person':<26} {'n':>3}  {'naive':>6}  {'ridge':>6}  {'rel':<4}"
        f"   {'calming':>{DIV_BAR_W}} 0 stress"
    )
    lines.append(pal.paint(header, GREY))
    max_score = max(abs(v) for _, v in board)
    for person, score in board:
        naive_mean, n = naive[person]
        width = _bar_width(score, max_score, DIV_BAR_W)
        if score >= 0:
            div = (
                " " * DIV_BAR_W + "|"
                + pal.paint(DIV_BAR * width, RED) + " " * (DIV_BAR_W - width)
            )
        else:
            div = (
                " " * (DIV_BAR_W - width) + pal.paint(DIV_BAR * width, GREEN)
                + "|" + " " * DIV_BAR_W
            )
        verdict, code = _verdict(score)
        if n < 4:
            verdict, code = "thin data", GREY
        lines.append(
            f"  {_short(person.split('@')[0], 26):<26} {n:>3}"
            f"  {naive_mean:+6.2f}"
            f"  {pal.signed(f'{score:+6.2f}', score)}"
            f"  {_reliability(n):<4}   {div}"
            f"  {pal.paint(verdict, code)}"
        )
    return "\n".join(lines)


def write_csvs(
    meeting_stats: list[MeetingStat],
    message_stats: list[MeetingStat],
    *,
    lam: float,
    min_meetings: int,
    out_dir: Path,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    meetings_csv = out_dir / "meeting_scores.csv"
    with meetings_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            ["start", "summary", "mean_hr", "baseline_hr", "elevation",
             "rel_elevation", "z", "n_samples", "attendees"]
        )
        for s in sorted(meeting_stats, key=lambda s: s.meeting.start):
            w.writerow(
                [datetime.fromtimestamp(s.meeting.start).isoformat(),
                 s.meeting.summary, f"{s.mean_hr:.1f}", f"{s.baseline_hr:.1f}",
                 f"{s.elevation:.2f}", f"{s.rel_elevation:.3f}", f"{s.z:.2f}",
                 s.n_samples, ";".join(sorted(s.meeting.attendees))]
            )

    persons_csv = out_dir / "person_scores.csv"
    with persons_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["board", "person", "n", "naive", "ridge", "verdict"])
        for board, stats in (("meetings", meeting_stats), ("slack", message_stats)):
            ridge = ridge_scores(stats, lam=lam, min_meetings=min_meetings)
            naive = naive_scores(stats, min_meetings=min_meetings)
            for person, score in sorted(ridge.items(), key=lambda kv: -kv[1]):
                naive_mean, n = naive[person]
                w.writerow(
                    [board, person, n, f"{naive_mean:.2f}", f"{score:.2f}",
                     _verdict(score)[0]]
                )
    return [meetings_csv, persons_csv]
