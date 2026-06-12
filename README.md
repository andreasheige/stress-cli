# stress

Which coworker spikes your heart rate? Matches per-minute Garmin heart-rate
data against your calendar events and attendees, scores each meeting's HR
elevation vs. its local baseline, and fits a ridge regression over attendee
presence to build a per-person stress leaderboard.

Inspired by [@the2ndfloorguy's Whoop experiment](https://x.com/the2ndfloorguy).

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
  - **Outlook / M365**: Settings → Calendar → *Shared calendars* → Publish a
    calendar with **"Can view all details"** (required for attendees) → ICS link
  - or a path to an exported `.ics` file

`config.toml` and all fetched data stay in this repo, gitignored.

## Usage

```bash
uv run stress fetch --days 30    # pull Garmin HR + calendar feeds into ./data
uv run stress report --days 30   # print meeting stats + the leaderboard
```

First `fetch` asks for your Garmin Connect login (MFA supported); tokens are
cached in `~/.garminconnect`, so subsequent runs are non-interactive.
HR data is cached per day, so re-fetching is cheap — run `fetch` daily or
weekly and `report` whenever you want the current standings.

Report options: `--top N` (meetings shown), `--ridge-lambda X`,
`--min-meetings N` (minimum shared meetings to appear on the board).

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
- Garmin HR granularity is roughly one sample per 1–2 minutes; very short
  meetings may be skipped for having too few samples.
- Outlook published calendars only include attendees at the
  "full details" permission level.

## Development

```bash
uv run pytest
```
