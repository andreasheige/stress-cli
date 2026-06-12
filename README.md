# stress

Which coworker spikes your heart rate? Matches per-minute heart-rate data
from your watch against your calendar events and attendees, scores each
meeting's HR elevation vs. its local baseline, and fits a ridge regression
over attendee presence to build a per-person stress leaderboard.

Inspired by [@the2ndfloorguy's Whoop experiment](https://x.com/the2ndfloorguy).

## Supported watches

| Watch | How | All-day HR? |
|---|---|---|
| Garmin | `stress fetch` (Garmin Connect API, login once) | yes |
| Apple Watch | `stress import export.zip` (Health → "Export All Health Data") | yes |
| Suunto | `stress import *.fit` (app activity export) | only recorded activities |
| Polar | `stress import *.tcx` / `*.fit` (Flow export) | only recorded activities |
| anything else | `stress import` any `.fit` / `.tcx` file | depends |

Meeting analysis needs HR during the workday, so Garmin and Apple Health are
the strong paths. FIT/TCX workout exports only cover recorded activities —
useful if your watch records all-day or you log long activity sessions at
your desk. A Polar AccessLink fetcher (continuous HR API) can be added if
someone needs it.

## Slack messages (optional)

Beyond meetings, the tool can rank people by what your heart rate does in
the 10 minutes after they DM or @mention you (outside meetings). Create a
personal Slack app at api.slack.com/apps, add user token scopes `im:read`,
`im:history`, `search:read`, `users:read`, `users:read.email`, install it to
your workspace, and put the user token (`xoxp-…`) in `config.toml` under
`[slack]` or in the `SLACK_TOKEN` env var. `stress fetch` then also pulls
messages (timestamps and senders only — message text is never stored) and
`stress report` shows a separate Slack leaderboard.

Microsoft Teams isn't supported: reading your chats requires a Microsoft
Graph app registration in your company's Azure tenant, which is usually
IT-gated. If you can get such a registration, a Teams fetcher would slot
into the same message pipeline.

## Setup

```bash
uv sync
cp config.example.toml config.toml   # then edit it
```

In `config.toml` you need:

- **`me`** — your own email addresses (so you don't rank yourself)
- **`calendars`** — one or more ICS sources:
  - **Google Calendar**: Settings → your calendar → *Integrate calendar* →
    "Secret address in iCal format"
  - **Outlook / M365**: Settings → Calendar → *Shared calendars* → Publish →
    ICS link. Note: Microsoft strips attendees from published feeds, so these
    meetings only count as busy time (excluded from baselines) and can't feed
    the leaderboard — that would require a Graph API app registration.
  - or a path to an exported `.ics` file

`config.toml` and all fetched data stay in this repo, gitignored.

## Usage

```bash
uv run stress fetch --days 30      # pull HR (API providers) + calendar feeds into ./data
uv run stress import export.zip    # or: import HR from exported files (.zip/.xml/.fit/.tcx)
uv run stress report --days 30     # print meeting stats + the leaderboard
```

All sources merge into the same per-day cache (`data/hr/`), deduped by
timestamp, so you can mix fetch and import freely.

For Garmin, the first `fetch` asks for your Garmin Connect login (MFA
supported); tokens are cached in `~/.garminconnect`, so subsequent runs are
non-interactive. HR data is cached per day, so re-fetching is cheap — run
`fetch` daily or weekly and `report` whenever you want the current standings.

Report options: `--top N` (meetings shown), `--ridge-lambda X`,
`--min-meetings N` (minimum shared meetings to appear on the board).
The report is colored when on a TTY (respects `NO_COLOR`) and also writes
`data/meeting_scores.csv` and `data/person_scores.csv` with the full numbers.

## How the scoring works

1. **Per meeting**: mean HR during the meeting minus the mean HR in the
   surrounding ±90 minutes of *non-meeting* time (back-to-back meetings
   don't pollute each other's baseline). Meetings without enough HR samples
   in both windows are skipped.
2. **Per person (naive)**: average elevation across all meetings they attend.
   Misleading when someone simply co-attends meetings with the real stressor.
3. **Per person (ridge)**: ridge regression of attendee presence against
   meeting elevation estimates each person's *marginal* effect, separating
   co-attendance confounding. This is what ranks the leaderboard.

## Caveats

- HR elevation isn't only stress: walking to a meeting room, coffee, or
  presenting all raise HR. Treat the leaderboard as entertainment with a
  hint of signal, not a performance review input.
- All-day HR granularity is roughly one sample per 1–2 minutes; very short
  meetings may be skipped for having too few samples.
- Outlook published calendars never include attendees; those meetings are
  used as busy time only.

## Development

```bash
uv run pytest
```
