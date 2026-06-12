"""CLI entry point: `stress fetch` pulls data, `stress report` prints the board."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from . import calendars, hrcache, messages, providers, report
from .analysis import compute_stats
from .config import load_config
from .providers import slack
from .report import Palette

DEFAULT_DAYS = 30


def cmd_fetch(args: argparse.Namespace) -> None:
    cfg = load_config()
    cal_dir = cfg.data_dir / "calendars"
    cal_dir.mkdir(parents=True, exist_ok=True)
    print(f"Fetching {len(cfg.calendars)} calendar feed(s)...")
    for i, source in enumerate(cfg.calendars):
        try:
            feed = calendars.load_ics(source)
        except (OSError, requests.RequestException) as exc:
            cached = (cal_dir / f"cal_{i}.ics").exists()
            note = "keeping cached copy" if cached else "no cached copy — feed will be missing"
            print(f"  calendar {i}: FAILED ({exc}) — {note}")
            continue
        (cal_dir / f"cal_{i}.ics").write_bytes(feed)
        print(f"  calendar {i}: {len(feed) // 1024} KiB")

    fetcher = providers.FETCHERS.get(cfg.provider)
    if fetcher is None:
        supported = ", ".join(sorted(providers.FETCHERS))
        sys.exit(
            f"Provider '{cfg.provider}' has no API fetcher (available: {supported}).\n"
            "For Apple Watch / Suunto / Polar, use `stress import` with exported files."
        )
    if cfg.slack_token:
        print(f"Fetching Slack DMs/@mentions for the last {args.days} days...")
        try:
            fetched_msgs = slack.fetch_messages(cfg.slack_token, args.days)
            total = messages.merge_messages(cfg.data_dir, fetched_msgs)
            print(f"  {len(fetched_msgs)} messages fetched, {total} cached in total.")
        except (RuntimeError, requests.RequestException) as exc:
            print(f"  Slack FAILED ({exc}) — continuing without messages.")

    print(f"Fetching {cfg.provider} heart rate for the last {args.days} days...")
    fetched = fetcher(args.days, cfg.data_dir / "hr")
    print(f"Done — {fetched} day(s) fetched, rest already cached.")


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

    pal = Palette(sys.stdout.isatty() and "NO_COLOR" not in os.environ)
    stats = compute_stats(meetings, samples, extra_busy=busy_only)

    cached_msgs = messages.load_messages(cfg.data_dir, args.days)
    events = messages.to_events(cached_msgs, past) if cached_msgs else []
    msg_stats = compute_stats(events, samples, extra_busy=past) if events else []

    print(
        report.render_intro(
            hrcache.day_counts(cfg.data_dir / "hr", args.days),
            days=args.days,
            n_meetings=len(meetings),
            n_attendees=len({a for m in meetings for a in m.attendees}),
            n_busy=len(busy_only),
            n_messages=len(cached_msgs),
            lam=args.ridge_lambda,
            pal=pal,
        )
    )
    print()
    print(report.render_meetings(stats, top=args.top, pal=pal))
    print()
    print(
        report.render_board(
            stats,
            title="PER-PERSON",
            subtitle="ranked by ridge marginal effect (bpm)",
            lam=args.ridge_lambda,
            min_meetings=args.min_meetings,
            pal=pal,
        )
    )
    if msg_stats:
        print()
        print(
            report.render_board(
                msg_stats,
                title="SLACK SENDERS",
                subtitle="HR effect in the 10 min after a message (outside meetings)",
                lam=args.ridge_lambda,
                min_meetings=args.min_meetings,
                pal=pal,
            )
        )
    paths = report.write_csvs(
        stats, msg_stats, lam=args.ridge_lambda,
        min_meetings=args.min_meetings, out_dir=cfg.data_dir,
    )
    print()
    print(pal.paint(f"wrote {', '.join(str(p) for p in paths)}", report.GREY))


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
