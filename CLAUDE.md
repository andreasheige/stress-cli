# CLAUDE.md

Stress leaderboard: matches wearable heart-rate data against calendar
meetings and Slack messages to rank which coworker raises the user's HR.
Python 3.12, managed with `uv`. Inspired by @the2ndfloorguy's Whoop tweet.

## Commands

```bash
uv run pytest                 # full test suite — run before every commit
uv run stress fetch --days N  # pull HR (Garmin) + calendars + Slack into ./data
uv run stress import <files>  # Apple Health .zip/.xml, .fit, .tcx into ./data
uv run stress report          # colored report + CSVs (data/*.csv)
```

The user has a `stressapp` zsh function aliasing `uv run stress` from anywhere.

## Architecture (src/stress/)

- `models.py` — `Meeting` (epoch seconds, attendee emails) and `MeetingStat`.
  Message events are converted into `Meeting`s so one pipeline scores both.
- `analysis.py` — per-meeting mean HR vs ±90 min *non-busy* baseline, then
  intercept-free ridge regression over attendee presence for marginal effects.
  `extra_busy` excludes intervals from baselines without scoring them.
- `calendars.py` — ICS parsing (icalendar + recurring-ical-events), dedupes
  the same event across feeds by UID and by (summary, start).
- `hrcache.py` — provider-agnostic day cache: `data/hr/YYYY-MM-DD.json` as
  `[[epoch_ms, bpm], ...]`, merged/deduped by timestamp.
- `providers/` — `garmin.py` (API fetch, registered in `FETCHERS`),
  `apple_health.py` + `workout_files.py` (file importers, dispatched by
  extension), `slack.py` (DMs + @mentions; stores only ts + sender, never text).
- `messages.py` — message cache; converts messages to 10-min pseudo-meetings
  (bursts merged, in-meeting messages dropped, windows clipped at meetings).
- `report.py` — ANSI report (OG-screenshot style) + CSV export. Pad plain
  text first, then color fragments — colored strings break `ljust`.
- `cli.py` — argparse; orchestrates fetch/import/report.

## Hard-won facts (do not re-derive)

- **garminconnect 0.3.5**: no `.garth` attribute. `Garmin(email, password,
  prompt_mfa=...).login(tokenstore)` loads AND persists tokens itself.
  Login 429s are per-strategy warnings — the 5-strategy chain continues;
  only "All login strategies rate limited" is fatal (wait or switch IP).
- **Google Calendar public ICS** strips all attendees except the owner —
  only the *secret* address (`/private-<key>/basic.ics`) includes them.
- **Outlook published ICS** never includes attendees; those meetings are
  busy-time only (routed via `extra_busy`).
- **Zero rows in the ridge design matrix are inert** (no intercept) — a past
  code review claimed they bias scores; verified false numerically.
- Intervals are half-open `[start, end)` everywhere.

## Secrets

`config.toml` and `data/` are gitignored — calendar ICS URLs act as bearer
tokens and the Slack token lives in config. **The user has twice pasted real
secrets into the tracked `config.example.toml` — check for that before any
commit, and keep real values in `config.toml` only.**

## Conventions

- Tests first for analysis/parsing logic; fetchers stay thin and untested.
- Conventional commits (`feat:`/`fix:`/`docs:`), no attribution trailers.
- Frozen dataclasses, half-open intervals, `pal.paint` only on non-empty text.
