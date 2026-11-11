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
