"""Fetch per-day heart-rate series from Garmin Connect and cache as JSON."""

from __future__ import annotations

import json
from datetime import date, timedelta
from getpass import getpass
from pathlib import Path

from garminconnect import Garmin

TOKEN_DIR = Path("~/.garminconnect").expanduser()


def get_client() -> Garmin:
    """Log in to Garmin Connect, reusing cached OAuth tokens when present."""
    try:
        client = Garmin()
        client.login(str(TOKEN_DIR))
        return client
    except FileNotFoundError:
        print("No cached Garmin tokens — logging in interactively.")
    except Exception as exc:
        # Expired/corrupt tokens raise library-specific errors; fall back to
        # interactive login but say why instead of failing silently.
        print(f"Cached token login failed ({type(exc).__name__}: {exc}) — logging in interactively.")

    email = input("Garmin email: ")
    password = getpass("Garmin password: ")
    client = Garmin(email=email, password=password, return_on_mfa=True)
    result, state = client.login()
    if result == "needs_mfa":
        mfa_code = input("Garmin MFA code: ")
        client.resume_login(state, mfa_code)
    client.garth.dump(str(TOKEN_DIR))
    print(f"Logged in; tokens cached in {TOKEN_DIR}")
    return client


def fetch_hr_days(client: Garmin, days: int, cache_dir: Path) -> int:
    """Download HR for the last `days` days into cache_dir, skipping cached days.

    Today is always refetched since its data is still growing.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    today = date.today()
    fetched = 0
    for offset in range(days):
        day = today - timedelta(days=offset)
        path = cache_dir / f"{day.isoformat()}.json"
        if path.exists() and day != today:
            continue
        data = client.get_heart_rates(day.isoformat())
        values = (data or {}).get("heartRateValues") or []
        path.write_text(json.dumps(values))
        fetched += 1
        print(f"  {day} — {len(values)} HR samples")
    return fetched


def load_samples(cache_dir: Path, days: int) -> list[tuple[float, float]]:
    """Load cached HR samples for the last `days` days as (epoch s, bpm)."""
    samples = []
    today = date.today()
    for offset in range(days):
        path = cache_dir / f"{(today - timedelta(days=offset)).isoformat()}.json"
        if not path.exists():
            continue
        for ts_ms, hr in json.loads(path.read_text()):
            if hr is not None:
                samples.append((ts_ms / 1000, float(hr)))
    return sorted(samples)
