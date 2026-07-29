"""
faceit.py — pull a player's CS2 matches + demos from the FACEIT Data API.

Lets a user "connect" their FACEIT account (by nickname) and have their recent
matches auto-analyzed through the same pipeline as a manual upload. Uses only
the public Data API (https://developers.faceit.com) with a server-side API key.

Set FACEIT_API_KEY in the environment (Railway → Variables). Without it the
feature stays cleanly disabled — enabled() returns False and the UI hides it.

stdlib only (urllib) so it adds no dependencies.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://open.faceit.com/data/v4"


def enabled() -> bool:
    return bool(os.getenv("FACEIT_API_KEY"))


class FaceitError(Exception):
    pass


def _get(path: str, params: dict | None = None) -> dict:
    key = os.getenv("FACEIT_API_KEY")
    if not key:
        raise FaceitError("FACEIT is not configured (no FACEIT_API_KEY).")
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise FaceitError("Not found on FACEIT.") from e
        if e.code in (401, 403):
            raise FaceitError("FACEIT API key rejected — check the key.") from e
        raise FaceitError(f"FACEIT API error {e.code}.") from e
    except urllib.error.URLError as e:
        raise FaceitError(f"Could not reach FACEIT: {e.reason}") from e


def find_player(nickname: str) -> dict:
    """Resolve a nickname to {player_id, nickname, avatar}. CS2 first, then
    fall back to a game-agnostic lookup (older accounts still list 'csgo')."""
    try:
        p = _get("/players", {"nickname": nickname, "game": "cs2"})
    except FaceitError:
        p = _get("/players", {"nickname": nickname})
    return {
        "player_id": p["player_id"],
        "nickname": p["nickname"],
        "avatar": p.get("avatar") or "",
    }


def recent_matches(player_id: str, limit: int = 10) -> list[dict]:
    """Most-recent finished CS2 matches: [{match_id, map, finished_at}...]."""
    data = _get(f"/players/{player_id}/history",
                {"game": "cs2", "offset": 0, "limit": limit})
    out = []
    for m in data.get("items", []):
        out.append({
            "match_id": m["match_id"],
            "finished_at": m.get("finished_at") or m.get("started_at") or 0,
            "map": (m.get("voting", {}).get("map", {}).get("pick", [None])
                    or [None])[0],
            "status": m.get("status", ""),
        })
    return out


def demo_url(match_id: str) -> str | None:
    """The downloadable demo URL for a match (first, if several)."""
    m = _get(f"/matches/{match_id}")
    urls = m.get("demo_url") or []
    return urls[0] if urls else None


def download_demo(url: str, dest) -> None:
    """Stream a (usually gzip) demo to dest. The pipeline decompresses it."""
    req = urllib.request.Request(url, headers={"User-Agent": "cs2-analyst"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as out:
        while chunk := r.read(1 << 20):
            out.write(chunk)
