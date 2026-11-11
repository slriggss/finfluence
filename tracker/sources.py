"""Sources: fetch what each one returns, and convert it to rows with the common columns.

Every source has a fetch function (returns the parsed payload, which is saved raw) and a normalize
function (payload -> list of {item_id, item, <numeric columns>}). Add a source by adding both to
SOURCES.
"""
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

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


# --- youtube_rss: each channel's public upload feed (no API key, a different endpoint from the API) ---

FEED_URL = "https://www.youtube.com/feeds/videos.xml"
ATOM = "{http://www.w3.org/2005/Atom}"
YT = "{http://www.youtube.com/xml/schemas/2015}"
MEDIA = "{http://search.yahoo.com/mrss/}"
WINDOW_DAYS = 7


def fetch_youtube_rss(roster, session=None):
    """One feed request per tracked channel; returns one XML document holding all the feeds.

    A channel whose feed fails is left out (the count shows it); if no feed works the source fails.
    Only what is tracked is kept per upload: video id, publish time and view count (not titles,
    descriptions or thumbnails), plus the channel's title.
    """
    get = (session or requests).get
    root = ET.Element("feeds", fetched=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    errors = []
    for r in roster:
        try:
            resp = get(FEED_URL, params={"channel_id": r["channel_id"]}, timeout=30,
                       headers={"User-Agent": "Mozilla/5.0 (finfluence tracker)"})
            resp.raise_for_status()
            feed = ET.fromstring(resp.content)
        except Exception as e:
            errors.append(f"{r['channel_id']}: {type(e).__name__}")
            continue
        out = ET.SubElement(root, "feed", channel_id=r["channel_id"], title=feed.findtext(ATOM + "title") or "")
        for entry in feed.findall(ATOM + "entry"):
            stats = entry.find(f"{MEDIA}group/{MEDIA}community/{MEDIA}statistics")
            ET.SubElement(out, "entry", id=entry.findtext(YT + "videoId") or "",
                          published=entry.findtext(ATOM + "published") or "",
                          views=(stats.get("views") if stats is not None else "") or "")
    if not len(root):
        raise RuntimeError(f"no feed could be read ({'; '.join(errors[:3])})")
    return ET.tostring(root, encoding="unicode")


def normalize_youtube_rss(payload):
    """Per channel: uploads in the 7 days before the fetch, days since the latest upload, and the
    mean views of the feed's recent uploads (the feed holds at most the 15 newest). Time is measured
    from the fetch time stored in the raw file, so the same raw file always gives the same rows."""
    root = ET.fromstring(payload)
    fetched = datetime.fromisoformat(root.get("fetched").replace("Z", "+00:00"))
    rows = []
    for feed in root.findall("feed"):
        ages, views = [], []
        for e in feed.findall("entry"):
            ages.append((fetched - datetime.fromisoformat(e.get("published"))).total_seconds() / 86400)
            if e.get("views"):
                views.append(int(e.get("views")))
        rows.append({
            "item_id": feed.get("channel_id"), "item": feed.get("title"),
            "videos_7d": sum(1 for a in ages if a <= WINDOW_DAYS),
            "days_since_upload": int(min(ages)) if ages else None,
            "recent_avg_views": round(sum(views) / len(views), 1) if views else None,
        })
    return rows


# --- youtube_videos: likes and comments on each channel's newest uploads (API key, two more endpoints) ---

UPLOADS_API = "https://www.googleapis.com/youtube/v3/playlistItems"
VIDEOS_API = "https://www.googleapis.com/youtube/v3/videos"
RECENT_VIDEOS = 15  # the same window as the upload feed: each channel's 15 newest uploads


def fetch_youtube_videos(roster, key=None, session=None):
    """The 15 newest uploads of each tracked channel, with their views, likes and comments.

    A channel's uploads are the playlist whose id is "UU" plus the channel id minus its "UC". One
    playlistItems.list call per channel, then one videos.list call per 50 videos. A channel whose
    playlist cannot be read is left out (the count shows it); if none can, the source fails. Only
    what is tracked is kept per video: id, publish time and the three counters (not titles,
    descriptions or thumbnails), plus the channel's title.
    """
    key = key or os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY is not set")
    get = (session or requests).get
    channels, errors = [], []
    for r in roster:
        cid = r["channel_id"]
        try:
            resp = get(UPLOADS_API, timeout=30, params={
                "part": "snippet,contentDetails", "playlistId": "UU" + cid[2:], "maxResults": RECENT_VIDEOS, "key": key})
            resp.raise_for_status()
            items = resp.json().get("items", [])
        except Exception as e:
            errors.append(f"{cid}: {type(e).__name__}")
            continue
        if not items:
            continue
        channels.append({"channel_id": cid, "title": items[0]["snippet"].get("channelTitle", ""),
                         "videos": [{"id": it["contentDetails"]["videoId"],
                                     "published": it["contentDetails"].get("videoPublishedAt", "")} for it in items]})
    if not channels:
        raise RuntimeError(f"no uploads could be read ({'; '.join(errors[:3]) or 'none found'})")
    ids = [v["id"] for c in channels for v in c["videos"]]
    stats = {}
    for i in range(0, len(ids), BATCH):
        resp = get(VIDEOS_API, timeout=30, params={"part": "statistics", "id": ",".join(ids[i:i + BATCH]), "key": key})
        resp.raise_for_status()
        for it in resp.json().get("items", []):
            stats[it["id"]] = it.get("statistics", {})
    for c in channels:
        for v in c["videos"]:
            s = stats.get(v["id"], {})
            v.update(views=s.get("viewCount"), likes=s.get("likeCount"), comments=s.get("commentCount"))
    return {"fetched": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "channels": channels}


def _total(videos, name):
    """The sum of one counter over the videos that report it; empty if none does (hidden or switched off)."""
    vals = [int(v[name]) for v in videos if v.get(name) not in (None, "")]
    return sum(vals) if vals else None


def normalize_youtube_videos(payload):
    """Per channel: the likes and the comments added up over its newest uploads."""
    return [{"item_id": c["channel_id"], "item": c["title"],
             "likes_recent": _total(c["videos"], "likes"), "comments_recent": _total(c["videos"], "comments")}
            for c in payload.get("channels", [])]


SOURCES = {
    "youtube": {"fetch": fetch_youtube, "normalize": normalize_youtube, "ext": "json"},
    "youtube_rss": {"fetch": fetch_youtube_rss, "normalize": normalize_youtube_rss, "ext": "xml"},
    "youtube_videos": {"fetch": fetch_youtube_videos, "normalize": normalize_youtube_videos, "ext": "json"},
}
