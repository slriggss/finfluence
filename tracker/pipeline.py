"""The daily run: fetch every source, build the history, write status, open the GitHub Issue.

Run:  uv run python -m tracker.pipeline [--date YYYY-MM-DD] [--no-issue]
"""
import argparse
import gzip
import json
import shutil
import subprocess
from datetime import datetime, timezone

from .build import DATA, build_history, build_status, load_raw, load_roster, read_history, write_history
from .moves import compute_moves
from .sources import SOURCES

ISSUE_LIMIT = 60000  # GitHub caps an issue body at 65,536 characters


def fetch_one(name, src, roster):
    """Return (payload or None, result). A failure is a result, never an exception."""
    try:
        payload = src["fetch"](roster)
        count = len(src["normalize"](payload))
        return payload, {"name": name, "ok": True, "count": count, "error": ""}
    except Exception as e:  # one source failing must not stop the run
        return None, {"name": name, "ok": False, "count": 0, "error": f"{type(e).__name__}: {e}"[:300]}


def fetch_all(date, roster, raw_dir=DATA / "raw", sources=SOURCES):
    """Pull every source and replace the day's raw files. Returns the per-source results.

    A source that fails writes no raw file, but its result is always recorded in results.json. If every
    source fails and the day already has raw files (from an earlier run the same day), those files and
    their results.json are kept as they were rather than wiped.
    """
    fetched = {name: fetch_one(name, src, roster) for name, src in sources.items()}
    results = [res for _, res in fetched.values()]
    day_dir = raw_dir / date
    if not any(r["ok"] for r in results):
        has_raw = day_dir.exists() and any(p.name != "results.json" for p in day_dir.iterdir())
        if not has_raw:  # record the failure; load_raw ignores a day folder with no raw file
            day_dir.mkdir(parents=True, exist_ok=True)
            (day_dir / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
        return results
    if day_dir.exists():
        shutil.rmtree(day_dir)
    day_dir.mkdir(parents=True)
    for name, (payload, res) in fetched.items():
        if payload is not None:
            text = json.dumps(payload, separators=(",", ":")) if sources[name]["ext"] == "json" else payload
            with gzip.GzipFile(day_dir / f"{name}.{sources[name]['ext']}.gz", "wb", mtime=0) as f:
                f.write(text.encode())
    (day_dir / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    return results


def fmt(n):
    return "" if n is None else f"{n:,}"


def issue_body(rows, date, results):
    prev, moves, appeared, disappeared = compute_moves(rows, date)
    failed = [r["name"] for r in results if not r["ok"]]
    lines = [f"Run for {date}."]
    if failed:
        lines.append(f"Sources that failed today: {', '.join(failed)}.")
    if prev is None:
        lines.append("First day with data, so there is nothing to compare against yet.")
    else:
        lines += [f"Biggest moves in total views since {prev} (top {len(moves)} by percent change):", "",
                  "| Channel | Views before | Views now | Change | Subscribers | New videos |",
                  "|---|---:|---:|---:|---:|---:|"]
        for m in moves:
            new_videos = (m["new_videos"] or 0) - (m["old_videos"] or 0)
            lines.append(f"| {m['item']} | {fmt(m['old_views'])} | {fmt(m['new_views'])} | {m['pct']:+.2f}% | "
                         f"{fmt(m['old_subscribers'])} → {fmt(m['new_subscribers'])} | {new_videos:+d} |")
        if not moves:
            lines.append("No item has a comparable value on both days.")
        lines += ["", f"Appeared: {', '.join(appeared) or 'none'}.", f"Disappeared: {', '.join(disappeared) or 'none'}."]
    return "\n".join(lines)[:ISSUE_LIMIT]


def gh(*args, body=None):
    """Run gh. A body goes through stdin (not argv) and a failure reports gh's own error text."""
    cmd = ["gh", *args] + (["--body-file", "-"] if body is not None else [])
    r = subprocess.run(cmd, input=body, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed ({r.returncode}): {r.stderr.strip()[:500]}")
    return r


def update_issue(date, body):
    """Open (or update) the issue titled with the date, and close every other open run issue."""
    listing = json.loads(gh("issue", "list", "--state", "all", "--limit", "100",
                            "--json", "number,title,state").stdout)
    mine = next((i for i in listing if i["title"] == date), None)
    if mine:
        gh("issue", "edit", str(mine["number"]), body=body)
        if mine["state"] != "OPEN":
            gh("issue", "reopen", str(mine["number"]))
    else:
        gh("issue", "create", "--title", date, body=body)
    for i in listing:
        if i["state"] == "OPEN" and i["title"] != date:
            gh("issue", "close", str(i["number"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="override the UTC run date (YYYY-MM-DD)")
    ap.add_argument("--no-issue", action="store_true")
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    date = args.date or now.strftime("%Y-%m-%d")

    roster = load_roster()
    results = fetch_all(date, roster)
    days = load_raw(DATA / "raw")
    rows = build_history(days, roster)
    write_history(rows, DATA / "history.csv")
    status = build_status(rows, days, now.strftime("%Y-%m-%dT%H:%M:%SZ"), results)
    (DATA / "status.json").write_text(json.dumps(status, indent=1), encoding="utf-8")
    for r in results:
        print(f"{'ok  ' if r['ok'] else 'FAIL'} {r['name']:<10} {r['count']:>4} {r['error']}")
    print(f"items={status['items']} new_today={status['new_today']} gone_today={status['gone_today']}")
    if not args.no_issue:
        try:  # never let the issue step cost the day's data
            update_issue(date, issue_body(read_history(DATA / "history.csv"), date, results))
        except Exception as e:
            print(f"::warning::issue update failed: {e}")


if __name__ == "__main__":
    main()
