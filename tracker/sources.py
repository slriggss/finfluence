"""Sources: fetch what each one returns, and convert it to rows with the common columns.

Every source has a fetch function (returns the parsed payload, which is saved raw) and a normalize
function (payload -> list of {item_id, item, <numeric columns>}). Add a source by adding both to
SOURCES.
"""
import os

import requests

YOUTUBE_API = "https://www.googleapis.com/youtube/v3/channels"
BATCH = 50  # the API takes at most 50 ids per call


def fetch_youtube(roster, key=None):
    """One channels.list call per 50 tracked channels. The API key travels only in the request."""
    key = key or os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY is not set")
    ids = [r["channel_id"] for r in roster]
    items = []
    for i in range(0, len(ids), BATCH):
        resp = requests.get(YOUTUBE_API, timeout=30, params={
            "part": "snippet,statistics", "id": ",".join(ids[i:i + BATCH]), "key": key})
        resp.raise_for_status()
        items += resp.json().get("items", [])
    # keep only the part we track: id, title and the counters (not thumbnails, descriptions, ...)
    return {"items": [{"id": it["id"], "title": it["snippet"]["title"], "statistics": it["statistics"]}
                      for it in items]}


def _count(stats, name):
    v = stats.get(name)
    return int(v) if v not in (None, "") else None


def normalize_youtube(payload):
    rows = []
    for it in payload.get("items", []):
        s = it.get("statistics", {})
        hidden = s.get("hiddenSubscriberCount", False)
        rows.append({
            "item_id": it["id"],
            "item": it["title"],
            "subscribers": None if hidden else _count(s, "subscriberCount"),
            "views": _count(s, "viewCount"),
            "videos": _count(s, "videoCount"),
        })
    return rows


SOURCES = {
    "youtube": {"fetch": fetch_youtube, "normalize": normalize_youtube, "ext": "json"},
}
