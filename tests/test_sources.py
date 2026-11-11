from conftest import channel, payload

from tracker.sources import normalize_youtube


def test_youtube_converts_to_common_columns():
    rows = normalize_youtube(payload(channel("UCa", "Alpha", 1500, 90000, 30)))
    assert rows == [{"item_id": "UCa", "item": "Alpha", "subscribers": 1500, "views": 90000, "videos": 30}]


def test_youtube_counts_arrive_as_strings_and_become_ints():
    row = normalize_youtube(payload(channel("UCa", "Alpha", "2000", "5", "1")))[0]
    assert (row["subscribers"], row["views"], row["videos"]) == (2000, 5, 1)


def test_youtube_hidden_subscriber_count_is_left_empty():
    row = normalize_youtube(payload(channel("UCa", "Alpha", 0, 10, 2, hidden=True)))[0]
    assert row["subscribers"] is None and row["views"] == 10


def test_youtube_missing_statistic_is_left_empty():
    p = {"items": [{"id": "UCa", "title": "Alpha", "statistics": {"viewCount": "7"}}]}
    row = normalize_youtube(p)[0]
    assert row["videos"] is None and row["subscribers"] is None


def test_youtube_empty_response_gives_no_rows():
    assert normalize_youtube({"items": []}) == []
    assert normalize_youtube({}) == []


# --- youtube_rss ---

from tracker.sources import fetch_youtube_rss, normalize_youtube_rss

FEEDS = """<feeds fetched="2026-11-10T12:00:00Z">
<feed channel_id="UCa" title="Alpha">
<entry id="v1" published="2026-11-10T06:00:00+00:00" views="100"/>
<entry id="v2" published="2026-11-05T12:00:00+00:00" views="300"/>
<entry id="v3" published="2026-10-01T12:00:00+00:00" views="200"/>
</feed>
<feed channel_id="UCb" title="Beta"/>
</feeds>"""


def test_rss_converts_to_common_columns():
    a, b = normalize_youtube_rss(FEEDS)
    assert a == {"item_id": "UCa", "item": "Alpha", "videos_7d": 2, "days_since_upload": 0, "recent_avg_views": 200.0}
    assert b["videos_7d"] == 0 and b["days_since_upload"] is None and b["recent_avg_views"] is None


def test_rss_same_raw_file_gives_same_rows():
    assert normalize_youtube_rss(FEEDS) == normalize_youtube_rss(FEEDS)


ATOM_FEED = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"
 xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/">
<title>Alpha</title><entry><yt:videoId>v1</yt:videoId><published>2026-11-10T06:00:00+00:00</published>
<title>secret title</title><media:group><media:community><media:statistics views="42"/></media:community></media:group>
</entry></feed>"""


class FakeResp:
    def __init__(self, content, status=200):
        self.content, self.status = content, status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(self.status)


class FakeSession:
    def __init__(self, by_id):
        self.by_id = by_id

    def get(self, url, params, **kw):
        return FakeResp(*self.by_id[params["channel_id"]])


def test_rss_fetch_keeps_only_tracked_parts_and_skips_a_failing_feed(roster):
    out = fetch_youtube_rss(roster, FakeSession({"UCa": (ATOM_FEED,), "UCb": (b"", 404)}))
    assert 'channel_id="UCa"' in out and 'views="42"' in out and 'id="v1"' in out
    assert "UCb" not in out and "secret title" not in out
    assert [r["item_id"] for r in normalize_youtube_rss(out)] == ["UCa"]


def test_rss_fetch_fails_when_no_feed_works(roster):
    import pytest
    with pytest.raises(RuntimeError):
        fetch_youtube_rss(roster, FakeSession({"UCa": (b"", 500), "UCb": (b"", 500)}))


# --- youtube_videos: likes and comments on each channel's newest uploads ---

from tracker.sources import fetch_youtube_videos, normalize_youtube_videos

VIDEOS = {"fetched": "2026-11-12T08:00:00Z", "channels": [
    {"channel_id": "UCa", "title": "Alpha", "videos": [
        {"id": "v1", "published": "2026-11-11T06:00:00Z", "views": "100", "likes": "10", "comments": "2"},
        {"id": "v2", "published": "2026-11-05T12:00:00Z", "views": "300", "likes": "30", "comments": None}]},
    {"channel_id": "UCb", "title": "Beta", "videos": [
        {"id": "v3", "published": "2026-11-01T12:00:00Z", "views": "5", "likes": None, "comments": None}]}]}


def test_videos_add_up_likes_and_comments_over_the_recent_uploads():
    a, b = normalize_youtube_videos(VIDEOS)
    assert a == {"item_id": "UCa", "item": "Alpha", "likes_recent": 40, "comments_recent": 2}
    assert b["likes_recent"] is None and b["comments_recent"] is None  # hidden or switched off: left empty


def test_videos_empty_payload_gives_no_rows():
    assert normalize_youtube_videos({}) == [] and normalize_youtube_videos({"channels": []}) == []


class FakeApi:
    """Answers playlistItems.list and videos.list like the API; a playlist id in `broken` fails."""
    def __init__(self, broken=()):
        self.broken, self.calls = set(broken), []

    def get(self, url, params, **kw):
        self.calls.append((url.rsplit("/", 1)[1], dict(params)))
        if url.endswith("playlistItems"):
            cid = "UC" + params["playlistId"][2:]
            if cid in self.broken:
                return FakeResp(b"", 404)
            body = {"items": [{"contentDetails": {"videoId": f"{cid}-v1", "videoPublishedAt": "2026-11-11T06:00:00Z"},
                               "snippet": {"channelTitle": f"T-{cid}", "title": "secret title", "description": "secret"}}]}
        else:
            body = {"items": [{"id": i, "statistics": {"viewCount": "9", "likeCount": "4", "commentCount": "1", "favoriteCount": "0"}}
                              for i in params["id"].split(",")]}
        r = FakeResp(b"")
        r.json = lambda: body
        return r


def test_videos_fetch_keeps_only_tracked_parts_and_never_stores_the_key(roster):
    api = FakeApi()
    out = fetch_youtube_videos(roster, key="SECRET-KEY", session=api)
    text = str(out)
    assert "SECRET-KEY" not in text and "secret" not in text and "favoriteCount" not in text
    assert [(c["channel_id"], c["title"]) for c in out["channels"]] == [("UCa", "T-UCa"), ("UCb", "T-UCb")]
    assert out["channels"][0]["videos"][0] == {"id": "UCa-v1", "published": "2026-11-11T06:00:00Z",
                                                "views": "9", "likes": "4", "comments": "1"}
    assert [c[0] for c in api.calls] == ["playlistItems", "playlistItems", "videos"]  # one call per channel, then one for the stats
    assert api.calls[0][1]["playlistId"] == "UUa" and api.calls[0][1]["maxResults"] == 15


def test_videos_fetch_skips_a_channel_that_fails_and_fails_when_none_work(roster):
    import pytest
    out = fetch_youtube_videos(roster, key="k", session=FakeApi(broken={"UCb"}))
    assert [r["item_id"] for r in normalize_youtube_videos(out)] == ["UCa"]
    with pytest.raises(RuntimeError):
        fetch_youtube_videos(roster, key="k", session=FakeApi(broken={"UCa", "UCb"}))


def test_videos_fetch_needs_a_key(roster, monkeypatch):
    import pytest
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="YOUTUBE_API_KEY"):
        fetch_youtube_videos(roster, session=FakeApi())
