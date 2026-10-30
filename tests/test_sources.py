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
