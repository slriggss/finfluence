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
