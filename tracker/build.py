"""Build data/history.csv and data/status.json from the raw files alone.

Run:  uv run python -m tracker.build
"""
import csv
import gzip
import json
from pathlib import Path

from .sources import SOURCES

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
COLUMNS = ["date", "item_id", "item", "source", "subscribers", "views", "videos", "views_per_video",
           "videos_7d", "days_since_upload", "recent_avg_views", "tier", "kind", "instagram", "youtube_handle"]
TIERS = [(1_000_000, "1M+"), (100_000, "100K-1M"), (10_000, "10K-100K"), (0, "under 10K")]


def load_roster(path=ROOT / "roster.csv"):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def tier(subscribers):
    if subscribers is None:
        return ""
    return next(label for floor, label in TIERS if subscribers >= floor)


def load_raw(raw_dir):
    """{date: {source: payload}} for every day folder that holds a raw file, in date order."""
    days = {}
    for day in sorted(p for p in Path(raw_dir).glob("*") if p.is_dir()):
        found = {}
        for name, src in SOURCES.items():
            f = day / f"{name}.{src['ext']}.gz"
            if f.exists():
                with gzip.open(f, "rt", encoding="utf-8") as fh:
                    found[name] = json.load(fh) if src["ext"] == "json" else fh.read()
        if found:
            days[day.name] = found
    return days


def convert_day(date, payloads, roster):
    """One row per item for one day, with the common columns.

    Each source fills the columns it reports; an item that several sources report gets one row whose
    `source` lists them (joined with "+") and whose columns hold whatever each reported. The item name
    comes from the first source in SOURCES order that has the item.
    """
    by_id = {r["channel_id"]: r for r in roster}
    merged = {}
    for name in SOURCES:  # fixed order, so the result does not depend on dict order of `payloads`
        if name not in payloads:
            continue
        for r in SOURCES[name]["normalize"](payloads[name]):
            m = merged.setdefault(r["item_id"], {"item": r["item"], "sources": []})
            m["sources"].append(name)
            m.update({k: v for k, v in r.items() if k not in ("item_id", "item")})
    rows = []
    for item_id, m in merged.items():
        meta = by_id.get(item_id, {})
        subs, views, videos = m.get("subscribers"), m.get("views"), m.get("videos")
        row = {"date": date, "item_id": item_id, "item": m["item"], "source": "+".join(m["sources"]),
               "subscribers": subs, "views": views, "videos": videos,
               "views_per_video": round(views / videos, 1) if views is not None and videos else None,
               "videos_7d": m.get("videos_7d"), "days_since_upload": m.get("days_since_upload"),
               "recent_avg_views": m.get("recent_avg_views"),
               "tier": tier(subs), "kind": meta.get("kind", ""),
               "instagram": meta.get("instagram", ""), "youtube_handle": meta.get("youtube_handle", "")}
        rows.append(row)
    return rows


def build_history(days, roster):
    rows = [row for date, payloads in days.items() for row in convert_day(date, payloads, roster)]
    return sorted(rows, key=lambda r: (r["date"], r["item_id"]))


def write_history(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in COLUMNS])


def read_history(path):
    """History rows with the numeric columns as numbers (empty -> None)."""
    num = {"subscribers": int, "views": int, "videos": int, "views_per_video": float,
           "videos_7d": int, "days_since_upload": int, "recent_avg_views": float}
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for c, cast in num.items():
            r[c] = cast(r[c]) if r[c] != "" else None
    return rows


def build_status(rows, days, run_time, results):
    dates = sorted(days)
    latest = dates[-1] if dates else None
    prev = dates[-2] if len(dates) > 1 else None
    ids = lambda d: {r["item_id"] for r in rows if r["date"] == d}
    now, before = (ids(latest) if latest else set()), (ids(prev) if prev else set())
    return {
        "run_time": run_time,
        "first_run_date": dates[0] if dates else None,
        "days_with_success": len(dates),
        "items": len(now),
        "new_today": len(now - before) if prev else 0,
        "gone_today": len(before - now),
        "sources": [{"name": r["name"], "ok": r["ok"], "count": r["count"]} for r in results],
    }


def main():
    days = load_raw(DATA / "raw")
    rows = build_history(days, load_roster())
    write_history(rows, DATA / "history.csv")
    print(f"{len(rows)} rows from {len(days)} days -> data/history.csv")


if __name__ == "__main__":
    main()
