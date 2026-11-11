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
    for col, key in (("subscribers", "subscribers_since_first"), ("views", "views_since_first"), ("videos", "videos_since_first")):
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

    # dashboard tiles: the total of a column on each date, and its change over the items present on both of the last two dates
    for col in ("subscribers", "views"):
        by_date = {}
        for r in rows:
            if r[col] is not None:
                by_date.setdefault(r["date"], {})[r["item_id"]] = r[col]
        assert [(t["date"], t["total"], t["n"]) for t in got[f"totals_{col}"]] == \
               [(d, sum(v.values()), len(v)) for d, v in sorted(by_date.items())]
        tc, days = got[f"total_change_{col}"], sorted({r["date"] for r in rows})
        if len(days) < 2:
            assert tc is None
            continue
        before, now = by_date.get(days[-2], {}), by_date.get(latest, {})
        common = [i for i in now if i in before]
        was, cur = sum(before[i] for i in common), sum(now[i] for i in common)
        assert (tc["prev"], tc["latest"], tc["n"]) == (days[-2], latest, len(common))
        assert (tc["was"], tc["now"], tc["change"]) == (was, cur, cur - was)
        assert tc["pct"] == (pytest.approx((cur - was) / was * 100) if was else None)

    # leaderboard: items ranked by percent growth since the previous date, best first
    for col in ("views", "subscribers"):
        lb, days = got[f"leaders_{col}"], sorted({r["date"] for r in rows})
        if len(days) < 2:
            assert lb["prev"] is None and lb["leaders"] == []
            continue
        by = {d: {r["item_id"]: r for r in rows if r["date"] == d and r[col] is not None} for d in (days[-2], latest)}
        expect = []
        for i, n in by[latest].items():
            o = by[days[-2]].get(i)
            if o and o[col]:
                expect.append((i, (n[col] - o[col]) / o[col] * 100, n[col] - o[col]))
        expect.sort(key=lambda e: (-e[1], -e[2], e[0]))
        assert lb["prev"] == days[-2]
        assert [(g["item_id"], pytest.approx(g["pct"])) for g in lb["leaders"]] == [(e[0], pytest.approx(e[1])) for e in expect]
        assert all(g["change"] == g["now"] - g["old"] for g in lb["leaders"])

    vpv = [r["views_per_video"] for r in rows if r["date"] == latest and r["views_per_video"] is not None]
    assert got["median_views_per_video"] == pytest.approx(statistics.median(vpv))


def test_fixture_numbers_match_the_history_file():
    check(FIXTURE)


def test_real_history_numbers_match_when_present():
    real = HERE.parent / "data" / "history.csv"
    if not real.exists() or real.read_text().count("\n") < 2:
        pytest.skip("no history yet")
    check(real)
