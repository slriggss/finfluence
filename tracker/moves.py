"""The move rule: which items moved the most since the previous run."""

TOP_N = 10


def pct(old, new):
    if old in (None, 0) or new is None:
        return None
    return (new - old) / old * 100


def compute_moves(rows, date, top_n=TOP_N):
    """Compare the rows of `date` with the latest earlier date in the history.

    A move is the percent change in total views. The top_n items by absolute percent change are
    listed (ties: larger absolute change in views, then item_id). Items present on only one of the
    two days are reported as appeared / disappeared, not as moves.
    Returns (previous_date or None, moves, appeared, disappeared).
    """
    earlier = sorted({r["date"] for r in rows if r["date"] < date})
    today = {r["item_id"]: r for r in rows if r["date"] == date}
    if not earlier:
        return None, [], [], []
    prev_date = earlier[-1]
    before = {r["item_id"]: r for r in rows if r["date"] == prev_date}
    moves = []
    for item_id, new in today.items():
        old = before.get(item_id)
        if old is None:
            continue
        change = pct(old["views"], new["views"])
        if change is None:
            continue
        moves.append({"item_id": item_id, "item": new["item"], "old_views": old["views"],
                      "new_views": new["views"], "pct": change,
                      "old_subscribers": old["subscribers"], "new_subscribers": new["subscribers"],
                      "old_videos": old["videos"], "new_videos": new["videos"]})
    moves.sort(key=lambda m: (-abs(m["pct"]), -abs(m["new_views"] - m["old_views"]), m["item_id"]))
    appeared = sorted(r["item"] for i, r in today.items() if i not in before)
    disappeared = sorted(r["item"] for i, r in before.items() if i not in today)
    return prev_date, moves[:top_n], appeared, disappeared
