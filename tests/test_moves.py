from tracker.moves import compute_moves, pct


def row(date, item_id, views, subs=100, videos=10, item=None):
    return {"date": date, "item_id": item_id, "item": item or item_id, "views": views,
            "subscribers": subs, "videos": videos}


def test_pct_change():
    assert pct(100, 150) == 50.0
    assert pct(200, 100) == -50.0
    assert pct(0, 5) is None and pct(None, 5) is None and pct(5, None) is None


def test_first_day_has_nothing_to_compare():
    assert compute_moves([row("2026-10-30", "a", 10)], "2026-10-30") == (None, [], [], [])


def test_moves_rank_by_absolute_percent_change():
    rows = [row("d1", "a", 1000), row("d1", "b", 1000), row("d1", "c", 1000),
            row("d2", "a", 1010), row("d2", "b", 800), row("d2", "c", 1100)]
    prev, moves, _, _ = compute_moves(rows, "d2")
    assert prev == "d1"
    assert [m["item_id"] for m in moves] == ["b", "c", "a"]  # -20%, +10%, +1%
    assert moves[0]["pct"] == -20.0


def test_only_top_n_are_listed():
    rows = [row("d1", str(i), 1000) for i in range(5)] + [row("d2", str(i), 1000 + i) for i in range(5)]
    _, moves, _, _ = compute_moves(rows, "d2", top_n=2)
    assert [m["item_id"] for m in moves] == ["4", "3"]


def test_ties_break_on_absolute_views_then_item_id():
    rows = [row("d1", "a", 100), row("d1", "b", 1000), row("d1", "c", 1000),
            row("d2", "a", 110), row("d2", "b", 1100), row("d2", "c", 1100)]
    _, moves, _, _ = compute_moves(rows, "d2")
    assert [m["item_id"] for m in moves] == ["b", "c", "a"]


def test_appeared_and_disappeared_are_not_moves():
    rows = [row("d1", "a", 100, item="Alpha"), row("d1", "gone", 100, item="Gone"),
            row("d2", "a", 100, item="Alpha"), row("d2", "new", 100, item="New")]
    prev, moves, appeared, disappeared = compute_moves(rows, "d2")
    assert [m["item_id"] for m in moves] == ["a"]
    assert appeared == ["New"] and disappeared == ["Gone"]


def test_compares_with_latest_earlier_date_even_if_a_day_was_skipped():
    rows = [row("2026-10-28", "a", 100), row("2026-10-30", "a", 200)]
    prev, moves, _, _ = compute_moves(rows, "2026-10-30")
    assert prev == "2026-10-28" and moves[0]["pct"] == 100.0


def test_item_with_no_comparable_views_is_skipped():
    rows = [row("d1", "a", 0), row("d2", "a", 5)]
    assert compute_moves(rows, "d2")[1] == []
