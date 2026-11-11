import gzip
import json

from conftest import channel, payload

from tracker import build
from tracker.pipeline import fetch_all


def write_day(raw, date, p):
    d = raw / date
    d.mkdir(parents=True)
    with gzip.GzipFile(d / "youtube.json.gz", "wb", mtime=0) as f:
        f.write(json.dumps(p).encode())


def two_days(tmp_path):
    raw = tmp_path / "raw"
    write_day(raw, "2026-10-30", payload(channel("UCb", "Beta", 20000, 500, 5), channel("UCa", "Alpha", 900, 100, 4)))
    write_day(raw, "2026-10-31", payload(channel("UCa", "Alpha", 950, 130, 5)))
    return raw


def test_history_has_fixed_first_four_columns():
    assert build.COLUMNS[:4] == ["date", "item_id", "item", "source"]


def test_rows_sorted_by_date_then_item_id(tmp_path, roster):
    rows = build.build_history(build.load_raw(two_days(tmp_path)), roster)
    assert [(r["date"], r["item_id"]) for r in rows] == [
        ("2026-10-30", "UCa"), ("2026-10-30", "UCb"), ("2026-10-31", "UCa")]


def test_static_and_derived_columns(tmp_path, roster):
    rows = build.build_history(build.load_raw(two_days(tmp_path)), roster)
    beta = rows[1]
    assert (beta["kind"], beta["instagram"], beta["tier"]) == ("company", "beta_ig", "10K-100K")
    assert beta["views_per_video"] == 100.0
    assert rows[0]["tier"] == "under 10K"


def test_day_with_no_file_has_no_rows(tmp_path, roster):
    raw = two_days(tmp_path)
    (raw / "2026-11-01").mkdir()  # a day folder with no raw file (e.g. a failed run's leftovers)
    days = build.load_raw(raw)
    assert list(days) == ["2026-10-30", "2026-10-31"]


def test_value_not_reported_is_left_empty_in_csv(tmp_path, roster):
    raw = tmp_path / "raw"
    write_day(raw, "2026-10-30", payload(channel("UCa", "Alpha", 0, 5, 1, hidden=True)))
    rows = build.build_history(build.load_raw(raw), roster)
    out = tmp_path / "h.csv"
    build.write_history(rows, out)
    assert build.read_history(out)[0]["subscribers"] is None
    assert ",,5,1," in out.read_text().splitlines()[1]


def test_rebuild_is_identical(tmp_path, roster):
    raw = two_days(tmp_path)
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    build.write_history(build.build_history(build.load_raw(raw), roster), a)
    build.write_history(build.build_history(build.load_raw(raw), roster), b)
    assert a.read_bytes() == b.read_bytes()


def test_status_counts(tmp_path, roster):
    raw = two_days(tmp_path)
    days = build.load_raw(raw)
    rows = build.build_history(days, roster)
    results = [{"name": "youtube", "ok": True, "count": 1, "error": ""}]
    s = build.build_status(rows, days, "2026-10-31T07:23:00Z", results)
    assert s["first_run_date"] == "2026-10-30" and s["days_with_success"] == 2
    assert (s["items"], s["new_today"], s["gone_today"]) == (1, 0, 1)
    assert s["sources"] == [{"name": "youtube", "ok": True, "count": 1}]


def test_first_day_new_today_is_zero(tmp_path, roster):
    raw = tmp_path / "raw"
    write_day(raw, "2026-10-30", payload(channel("UCa", "Alpha", 1, 1, 1)))
    days = build.load_raw(raw)
    s = build.build_status(build.build_history(days, roster), days, "t", [])
    assert (s["items"], s["new_today"], s["gone_today"]) == (1, 0, 0)


# --- the pipeline's fetch step: failure handling and the second run on the same day ---

def source(result, normalize=lambda p: p["items"]):
    def fetch(roster):
        if isinstance(result, Exception):
            raise result
        return result
    return {"fetch": fetch, "normalize": normalize, "ext": "json"}


def test_failed_source_writes_no_raw_file_and_is_recorded(tmp_path, roster):
    sources = {"youtube": source(RuntimeError("quota")), "other": source({"items": [1, 2]})}
    results = fetch_all("2026-10-30", roster, tmp_path, sources)
    assert not (tmp_path / "2026-10-30" / "youtube.json.gz").exists()
    assert (tmp_path / "2026-10-30" / "other.json.gz").exists()
    by = {r["name"]: r for r in results}
    assert by["youtube"]["ok"] is False and "quota" in by["youtube"]["error"]
    assert by["other"]["ok"] is True and by["other"]["count"] == 2
    saved = json.loads((tmp_path / "2026-10-30" / "results.json").read_text())
    assert len(saved) == 2


def test_second_run_same_day_replaces_the_days_files(tmp_path, roster):
    fetch_all("2026-10-30", roster, tmp_path, {"youtube": source(payload(channel("UCa", "Alpha", 1, 100, 1)))})
    fetch_all("2026-10-30", roster, tmp_path, {"youtube": source(payload(channel("UCa", "Alpha", 1, 250, 1)))})
    days = build.load_raw(tmp_path)
    assert list(days) == ["2026-10-30"]  # one day, counted once
    rows = build.build_history(days, roster)
    assert len(rows) == 1 and rows[0]["views"] == 250


def test_second_run_building_history_again_does_not_duplicate_rows(tmp_path, roster):
    p = payload(channel("UCa", "Alpha", 1, 100, 1))
    for _ in range(2):
        fetch_all("2026-10-30", roster, tmp_path, {"youtube": source(p)})
        rows = build.build_history(build.load_raw(tmp_path), roster)
    assert len(rows) == 1


def test_all_sources_failing_keeps_the_days_earlier_files(tmp_path, roster):
    fetch_all("2026-10-30", roster, tmp_path, {"youtube": source(payload(channel("UCa", "Alpha", 1, 100, 1)))})
    results = fetch_all("2026-10-30", roster, tmp_path, {"youtube": source(RuntimeError("down"))})
    assert results[0]["ok"] is False
    assert list(build.load_raw(tmp_path)) == ["2026-10-30"]


def test_all_sources_failing_on_a_new_day_creates_no_day(tmp_path, roster):
    fetch_all("2026-10-30", roster, tmp_path, {"youtube": source(RuntimeError("down"))})
    assert build.load_raw(tmp_path) == {}


def test_all_sources_failing_still_records_the_result(tmp_path, roster):
    fetch_all("2026-10-30", roster, tmp_path, {"youtube": source(RuntimeError("down"))})
    saved = json.loads((tmp_path / "2026-10-30" / "results.json").read_text())
    assert saved[0]["name"] == "youtube" and saved[0]["ok"] is False and "down" in saved[0]["error"]
    assert not list((tmp_path / "2026-10-30").glob("*.gz"))


# --- two sources: merged rows, and one source failing ---

RSS = '<feeds fetched="2026-10-30T12:00:00Z"><feed channel_id="UCa" title="Alpha">' \
      '<entry id="v" published="2026-10-29T12:00:00+00:00" views="10"/></feed></feeds>'


def write_rss(raw, date, text):
    with gzip.GzipFile(raw / date / "youtube_rss.xml.gz", "wb", mtime=0) as f:
        f.write(text.encode())


def test_two_sources_merge_into_one_row_per_item(tmp_path, roster):
    raw = tmp_path / "raw"
    write_day(raw, "2026-10-30", payload(channel("UCa", "Alpha", 900, 100, 4)))
    write_rss(raw, "2026-10-30", RSS)
    rows = build.build_history(build.load_raw(raw), roster)
    assert len(rows) == 1
    assert rows[0]["source"] == "youtube+youtube_rss"
    assert (rows[0]["views"], rows[0]["videos_7d"], rows[0]["days_since_upload"]) == (100, 1, 1)


def test_one_source_failing_leaves_the_other_sources_columns_empty(tmp_path, roster):
    raw = tmp_path / "raw"
    write_day(raw, "2026-10-30", payload(channel("UCa", "Alpha", 900, 100, 4)))
    write_day(raw, "2026-10-31", payload())  # API day with no items
    write_rss(raw, "2026-10-31", RSS.replace("2026-10-30", "2026-10-31").replace("29", "30"))
    rows = build.build_history(build.load_raw(raw), roster)
    day2 = [r for r in rows if r["date"] == "2026-10-31"][0]
    assert day2["source"] == "youtube_rss" and day2["views"] is None and day2["videos_7d"] == 1


def test_fetch_all_survives_one_failing_source_and_saves_xml(tmp_path, roster):
    sources = {"youtube": source(RuntimeError("quota")),
               "youtube_rss": {"fetch": lambda r: RSS, "normalize": lambda p: [1], "ext": "xml"}}
    results = fetch_all("2026-10-30", roster, tmp_path, sources)
    assert [r["ok"] for r in results] == [False, True]
    with gzip.open(tmp_path / "2026-10-30" / "youtube_rss.xml.gz", "rt") as f:
        assert f.read() == RSS


# --- the third source: likes and comments ---

def write_videos(raw, date, payload_):
    with gzip.GzipFile(raw / date / "youtube_videos.json.gz", "wb", mtime=0) as f:
        f.write(json.dumps(payload_).encode())


VIDEOS = {"fetched": "2026-10-30T12:00:00Z", "channels": [{"channel_id": "UCa", "title": "Alpha", "videos": [
    {"id": "v1", "published": "2026-10-29T12:00:00Z", "views": "10", "likes": "7", "comments": "3"}]}]}


def test_three_sources_merge_into_one_row_with_likes_and_comments(tmp_path, roster):
    raw = tmp_path / "raw"
    write_day(raw, "2026-10-30", payload(channel("UCa", "Alpha", 900, 100, 4)))
    write_rss(raw, "2026-10-30", RSS)
    write_videos(raw, "2026-10-30", VIDEOS)
    rows = build.build_history(build.load_raw(raw), roster)
    assert len(rows) == 1 and rows[0]["source"] == "youtube+youtube_rss+youtube_videos"
    assert (rows[0]["likes_recent"], rows[0]["comments_recent"], rows[0]["views"]) == (7, 3, 100)


def test_a_day_without_the_videos_source_leaves_likes_and_comments_empty_and_history_round_trips(tmp_path, roster):
    raw = tmp_path / "raw"
    write_day(raw, "2026-10-30", payload(channel("UCa", "Alpha", 900, 100, 4)))
    rows = build.build_history(build.load_raw(raw), roster)
    assert rows[0]["likes_recent"] is None and rows[0]["comments_recent"] is None
    path = tmp_path / "history.csv"
    build.write_history(rows, path)
    assert build.read_history(path) == rows
