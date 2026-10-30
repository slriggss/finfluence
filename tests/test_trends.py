"""The Trends/Today page numbers (calc.js, run by Node) must agree with data/history.csv.

Each figure is recomputed here in plain Python from the CSV and compared with what calc.js returns.
"""
import json
import shutil
import statistics
import subprocess
from pathlib import Path

import pytest

from tracker.build import read_history
from tracker.moves import compute_moves

HERE = Path(__file__).parent
FIXTURE = HERE / "fixture_history.csv"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def js(path):
    out = subprocess.run(["node", str(HERE / "trends_check.js"), str(path)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def series(rows, col):
    out = {}
    for r in sorted(rows, key=lambda r: r["date"]):
        if r[col] is not None:
            out.setdefault(r["item_id"], []).append((r["date"], r[col], r["item"]))
    return out


def check(path):
    rows, got = read_history(path), js(path)
    latest = max(r["date"] for r in rows)
    assert got["latest"] == latest

    # the move rule agrees with the pipeline's Python implementation
    prev, moves, _, _ = compute_moves(rows, latest)
    assert got["moves"]["prev"] == prev
    assert [(m["item_id"], pytest.approx(m["pct"])) for m in got["moves"]["moves"]] == \
           [(m["item_id"], pytest.approx(m["pct"])) for m in moves]

    # growth since the first run, per item
    for col, key in (("subscribers", "subscribers_since_first"), ("videos", "videos_since_first")):
        expect = {i: (p[0], p[-1]) for i, p in series(rows, col).items() if len(p) > 1}
        assert {g["item_id"] for g in got[key]} == set(expect)
        for g in got[key]:
            (d0, v0, _), (d1, v1, _) = expect[g["item_id"]]
            assert (g["from"], g["to"], g["first"], g["last"], g["change"]) == (d0, d1, v0, v1, v1 - v0)
            assert g["pct"] == (pytest.approx((v1 - v0) / v0 * 100) if v0 else None)

    # biggest gain between consecutive dates, per item
    for g in got["views_gains"]:
        p = series(rows, "views")[g["item_id"]]
        gains = [(b[1] - a[1], b[0]) for a, b in zip(p, p[1:])]
        best = max(gains, key=lambda x: x[0])
        assert (g["gain"], g["date"]) == (best[0], best[1])

    # spread of subscribers on the latest date
    vals = {r["item"]: r["subscribers"] for r in rows if r["date"] == latest and r["subscribers"] is not None}
    sp = got["spread_subscribers"]
    med = statistics.median(vals.values())
    assert sp["n"] == len(vals) and sp["median"] == med
    assert sp["top"]["subscribers"] == max(vals.values()) and sp["bottom"]["subscribers"] == min(vals.values())
    assert sp["topToMedian"] == pytest.approx(max(vals.values()) / med)

    vpv = [r["views_per_video"] for r in rows if r["date"] == latest and r["views_per_video"] is not None]
    assert got["median_views_per_video"] == pytest.approx(statistics.median(vpv))


def test_fixture_numbers_match_the_history_file():
    check(FIXTURE)


def test_real_history_numbers_match_when_present():
    real = HERE.parent / "data" / "history.csv"
    if not real.exists() or real.read_text().count("\n") < 2:
        pytest.skip("no history yet")
    check(real)
