"""Fetch Slack messages directed at you: DMs and @mentions.

Needs a user token (xoxp-…) from a personal Slack app with scopes:
im:read, im:history, search:read, users:read, users:read.email.
Only timestamps and senders are kept — message text is never stored.
Senders resolve to their email when available, so the same person matches
across the Slack board and the meeting board.
"""

from __future__ import annotations

import time

import requests

from ..messages import Message

API = "https://slack.com/api"
TIMEOUT_S = 30
PAGE_SIZE = 200


def _call(token: str, method: str, **params) -> dict:
    resp = requests.get(
        f"{API}/{method}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=TIMEOUT_S,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack {method} failed: {data.get('error')}")
    return data


def _paginate(token: str, method: str, key: str, **params):
    cursor = None
    while True:
        data = _call(token, method, limit=PAGE_SIZE, **params, **(
            {"cursor": cursor} if cursor else {}
        ))
        yield from data.get(key, [])
        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            return


def _dm_senders(token: str, my_id: str, oldest: float) -> list[tuple[float, str]]:
    found = []
    for channel in _paginate(token, "users.conversations", "channels", types="im"):
        for m in _paginate(
            token, "conversations.history", "messages",
            channel=channel["id"], oldest=str(oldest),
        ):
            if m.get("type") == "message" and not m.get("subtype") and m.get("user") not in (None, my_id):
                found.append((float(m["ts"]), m["user"]))
    return found


def _mention_senders(token: str, my_id: str, oldest: float) -> list[tuple[float, str]]:
    found = []
    page = 1
    while True:
        data = _call(token, "search.messages", query=f"<@{my_id}>", count=100, page=page)
        matches = data["messages"]["matches"]
        for m in matches:
            ts = float(m["ts"])
            if ts >= oldest and m.get("user") not in (None, my_id):
                found.append((ts, m["user"]))
        paging = data["messages"]["paging"]
        if page >= paging["pages"]:
            return found
        page += 1


def _resolve_users(token: str, user_ids: set[str]) -> dict[str, str]:
    names = {}
    for uid in user_ids:
        try:
            user = _call(token, "users.info", user=uid)["user"]
            names[uid] = (user.get("profile", {}).get("email") or user.get("real_name") or uid).lower()
        except RuntimeError:
            names[uid] = uid  # deactivated user etc. — keep the raw id
    return names


def fetch_messages(token: str, days: int) -> list[Message]:
    my_id = _call(token, "auth.test")["user_id"]
    oldest = time.time() - days * 86400

    raw = _dm_senders(token, my_id, oldest)
    try:
        raw += _mention_senders(token, my_id, oldest)
    except RuntimeError as exc:
        print(f"  skipping @mentions ({exc}) — DMs only")

    names = _resolve_users(token, {uid for _, uid in raw})
    return [Message(ts=ts, sender=names[uid], source="slack") for ts, uid in raw]
