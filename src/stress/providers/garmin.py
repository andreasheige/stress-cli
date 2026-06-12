"""Fetch per-day heart-rate series from Garmin Connect into the day cache."""

from __future__ import annotations

from datetime import date, timedelta
from getpass import getpass
from pathlib import Path

from garminconnect import Garmin

from .. import hrcache

TOKEN_DIR = Path("~/.garminconnect").expanduser()


def _get_client() -> Garmin:
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
    client = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("Garmin MFA code: "),
    )
    # Passing the tokenstore makes the library persist tokens on success,
    # so subsequent runs never hit the (rate-limited) SSO login again.
    client.login(str(TOKEN_DIR))
    print(f"Logged in; tokens cached in {TOKEN_DIR}")
    return client


def fetch_days(days: int, cache_dir: Path) -> int:
    """Download HR for the last `days` days into the cache, skipping cached days.

    Today is always refetched since its data is still growing.
    """
    client = _get_client()
    today = date.today()
    fetched = 0
    for offset in range(days):
        day = today - timedelta(days=offset)
        if hrcache.day_path(cache_dir, day).exists() and day != today:
            continue
        data = client.get_heart_rates(day.isoformat())
        values = (data or {}).get("heartRateValues") or []
        count = hrcache.merge_day(cache_dir, day, values)
        fetched += 1
        print(f"  {day} — {count} HR samples")
    return fetched
