"""CLI entry point: `stress fetch` pulls data, `stress report` prints the board."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import calendars, hrcache, messages, providers
from .analysis import compute_stats
from .config import load_config
from .providers import slack
from .report import render, render_messages

DEFAULT_DAYS = 30


def cmd_fetch(args: argparse.Namespace) -> None:
    cfg = load_config()
    cal_dir = cfg.data_dir / "calendars"
    cal_dir.mkdir(parents=True, exist_ok=True)
    print(f"Fetching {len(cfg.calendars)} calendar feed(s)...")
    for i, source in enumerate(cfg.calendars):
        feed = calendars.load_ics(source)
        (cal_dir / f"cal_{i}.ics").write_bytes(feed)
        print(f"  calendar {i}: {len(feed) // 1024} KiB")

    fetcher = providers.FETCHERS.get(cfg.provider)
    if fetcher is None:
        supported = ", ".join(sorted(providers.FETCHERS))
        sys.exit(
            f"Provider '{cfg.provider}' has no API fetcher (available: {supported}).\n"
            "For Apple Watch / Suunto / Polar, use `stress import` with exported files."
        )
    print(f"Fetching {cfg.provider} heart rate for the last {args.days} days...")
    fetched = fetcher(args.days, cfg.data_dir / "hr")
    print(f"Done — {fetched} day(s) fetched, rest already cached.")

    if cfg.slack_token:
        print(f"Fetching Slack DMs/@mentions for the last {args.days} days...")
        fetched_msgs = slack.fetch_messages(cfg.slack_token, args.days)
        total = messages.merge_messages(cfg.data_dir, fetched_msgs)
        print(f"  {len(fetched_msgs)} messages fetched, {total} cached in total.")


def cmd_import(args: argparse.Namespace) -> None:
    cfg = load_config()
    for path in args.files:
        samples = providers.import_file(Path(path))
        if not samples:
            print(f"  {path}: no heart-rate samples found")
            continue
        merged = hrcache.merge_samples(cfg.data_dir / "hr", samples)
        days = f"{min(merged)} … {max(merged)}" if len(merged) > 1 else str(min(merged))
        print(f"  {path}: {len(samples)} samples across {len(merged)} day(s) ({days})")


def cmd_report(args: argparse.Namespace) -> None:
    cfg = load_config()
    cal_dir = cfg.data_dir / "calendars"
    feeds = sorted(cal_dir.glob("cal_*.ics"))
    if not feeds:
        sys.exit("No cached data found — run `stress fetch` first.")

    window_end = datetime.now(timezone.utc)
    window_start = window_end - timedelta(days=args.days)
    meetings = calendars.parse_meetings(
        [f.read_bytes() for f in feeds], window_start, window_end, my_emails=cfg.my_emails
    )
    # Events with no other attendees (focus blocks, feeds that strip
    # attendees like published Outlook calendars) can't be attributed to
    # people, but still count as busy time excluded from baselines.
    # Future meetings have no HR yet.
    now_ts = window_end.timestamp()
    past = [m for m in meetings if m.end <= now_ts]
    meetings = [m for m in past if m.attendees]
    busy_only = [m for m in past if not m.attendees]

    samples = hrcache.load_samples(cfg.data_dir / "hr", args.days)
    if not samples:
        sys.exit("No heart-rate data cached — run `stress fetch` first.")

    stats = compute_stats(meetings, samples, extra_busy=busy_only)
    attendee_count = len({a for m in meetings for a in m.attendees})
    print(
        f"STRESS REPORT — last {args.days} days · {len(meetings)} meetings "
        f"(+{len(busy_only)} without attendee info), "
        f"{len(stats)} scored (HR coverage) · {attendee_count} attendees · "
        f"{len(samples)} HR samples\n"
    )
    print(render(stats, lam=args.ridge_lambda, min_meetings=args.min_meetings, top=args.top))

    cached_msgs = messages.load_messages(cfg.data_dir, args.days)
    if cached_msgs:
        events = messages.to_events(cached_msgs, past)
        msg_stats = compute_stats(events, samples, extra_busy=past)
        print()
        print(render_messages(msg_stats, lam=args.ridge_lambda, min_meetings=args.min_meetings))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="stress", description="Which coworker spikes your heart rate?"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="pull HR (API providers) + calendar feeds into ./data")
    fetch.add_argument("--days", type=int, default=DEFAULT_DAYS)
    fetch.set_defaults(func=cmd_fetch)

    imp = sub.add_parser(
        "import",
        help="import HR from exported files: Apple Health .zip/.xml, .fit, .tcx",
    )
    imp.add_argument("files", nargs="+", help="export files to import")
    imp.set_defaults(func=cmd_import)

    cfg_defaults = load_config_defaults()
    report = sub.add_parser("report", help="print meeting stats and the leaderboard")
    report.add_argument("--days", type=int, default=DEFAULT_DAYS)
    report.add_argument("--top", type=int, default=15, help="meetings to show")
    report.add_argument(
        "--ridge-lambda", type=float, default=cfg_defaults[0], dest="ridge_lambda"
    )
    report.add_argument("--min-meetings", type=int, default=cfg_defaults[1])
    report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


def load_config_defaults() -> tuple[float, int]:
    """Analysis defaults from config.toml when present, else library defaults."""
    from .analysis import DEFAULT_LAMBDA, DEFAULT_MIN_MEETINGS
    from .config import CONFIG_PATH

    if not CONFIG_PATH.exists():
        return DEFAULT_LAMBDA, DEFAULT_MIN_MEETINGS
    cfg = load_config()
    return cfg.lam, cfg.min_meetings
