// Pure functions on the history rows. Shared by the pages and by tests/trends_check.js (Node),
// so the numbers on the Trends page can be checked against data/history.csv.
(function (root) {
  const NUM = ["subscribers", "views", "videos", "views_per_video", "videos_7d", "days_since_upload", "recent_avg_views", "likes_recent", "comments_recent"];

  function parseCSV(text) {
    const rows = []; let row = [], cell = "", q = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (q) {
        if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; }
        else cell += c;
      } else if (c === '"') q = true;
      else if (c === ",") { row.push(cell); cell = ""; }
      else if (c === "\n" || c === "\r") {
        if (c === "\r" && text[i + 1] === "\n") i++;
        row.push(cell); cell = ""; rows.push(row); row = [];
      } else cell += c;
    }
    if (cell || row.length) { row.push(cell); rows.push(row); }
    const head = rows.shift();
    return rows.filter(r => r.length === head.length).map(r => {
      const o = Object.fromEntries(head.map((h, i) => [h, r[i]]));
      for (const c of NUM) o[c] = o[c] == null || o[c] === "" ? null : Number(o[c]);  // a column the file does not have yet is empty too
      return o;
    });
  }

  const dates = rows => [...new Set(rows.map(r => r.date))].sort();
  const latestDate = rows => dates(rows).pop() || "";
  const onDate = (rows, d) => rows.filter(r => r.date === d);

  // item_id -> [{date, value}] with empty values dropped, in date order
  function seriesByItem(rows, col) {
    const m = new Map();
    for (const r of rows) {
      if (r[col] == null) continue;
      if (!m.has(r.item_id)) m.set(r.item_id, { item_id: r.item_id, item: r.item, points: [] });
      m.get(r.item_id).points.push({ date: r.date, value: r[col] });
    }
    for (const s of m.values()) s.points.sort((a, b) => (a.date < b.date ? -1 : 1));
    return m;
  }

  const pct = (a, b) => (a == null || b == null || a === 0 ? null : ((b - a) / a) * 100);

  // The move rule: percent change in total views against the latest earlier date.
  function moves(rows, date, topN = 10) {
    const earlier = dates(rows).filter(d => d < date);
    if (!earlier.length) return { prev: null, moves: [] };
    const prev = earlier[earlier.length - 1];
    const before = new Map(onDate(rows, prev).map(r => [r.item_id, r]));
    const out = [];
    for (const n of onDate(rows, date)) {
      const o = before.get(n.item_id);
      if (!o) continue;
      const p = pct(o.views, n.views);
      if (p == null) continue;
      out.push({ item_id: n.item_id, item: n.item, old: o.views, now: n.views, pct: p });
    }
    out.sort((a, b) => Math.abs(b.pct) - Math.abs(a.pct) || Math.abs(b.now - b.old) - Math.abs(a.now - a.old) ||
      (a.item_id < b.item_id ? -1 : 1));
    return { prev, moves: out.slice(0, topN) };
  }

  // The leaderboard: items ranked by percent growth of `col` from the latest earlier date to the latest date, best first.
  // Only items with a value on both dates count. Ties go to the bigger absolute gain, then to item_id.
  function leaders(rows, col, topN = 3) {
    const latest = latestDate(rows), earlier = dates(rows).filter(d => d < latest);
    if (!earlier.length) return { prev: null, leaders: [], comparable: 0 };
    const prev = earlier[earlier.length - 1];
    const before = new Map(onDate(rows, prev).filter(r => r[col] != null).map(r => [r.item_id, r[col]]));
    const out = [];
    for (const n of onDate(rows, latest)) {
      if (n[col] == null || !before.has(n.item_id)) continue;
      const old = before.get(n.item_id), p = pct(old, n[col]);
      if (p == null) continue;
      out.push({ item_id: n.item_id, item: n.item, old, now: n[col], change: n[col] - old, pct: p });
    }
    out.sort((a, b) => b.pct - a.pct || b.change - a.change || (a.item_id < b.item_id ? -1 : 1));
    return { prev, leaders: out.slice(0, topN), comparable: out.length };  // comparable: items with a value on both dates
  }

  // Change from each item's first to its latest value of `col` (items with fewer than two values skipped).
  function sinceFirst(rows, col) {
    const out = [];
    for (const s of seriesByItem(rows, col).values()) {
      if (s.points.length < 2) continue;
      const a = s.points[0], b = s.points[s.points.length - 1];
      out.push({ item_id: s.item_id, item: s.item, from: a.date, to: b.date, first: a.value, last: b.value,
                 change: b.value - a.value, pct: pct(a.value, b.value) });
    }
    return out;
  }

  // The largest increase between two consecutive values of each item.
  function biggestGains(rows, col) {
    const out = [];
    for (const s of seriesByItem(rows, col).values()) {
      let best = null;
      for (let i = 1; i < s.points.length; i++) {
        const gain = s.points[i].value - s.points[i - 1].value;
        if (!best || gain > best.gain) best = { gain, date: s.points[i].date, from: s.points[i - 1].date };
      }
      if (best) out.push({ item_id: s.item_id, item: s.item, ...best });
    }
    return out;
  }

  const median = xs => {
    const v = [...xs].sort((a, b) => a - b), n = v.length;
    return n ? (n % 2 ? v[(n - 1) / 2] : (v[n / 2 - 1] + v[n / 2]) / 2) : null;
  };

  // How far apart the items are on the latest date.
  function spread(rows, col) {
    const vals = onDate(rows, latestDate(rows)).filter(r => r[col] != null);
    if (!vals.length) return null;
    const sorted = [...vals].sort((a, b) => b[col] - a[col]);
    const top = sorted[0], bottom = sorted[sorted.length - 1], med = median(vals.map(r => r[col]));
    return { date: latestDate(rows), n: vals.length, top, bottom, median: med,
             topToMedian: med ? top[col] / med : null, topToBottom: bottom[col] ? top[col] / bottom[col] : null };
  }

  // The sum of `col` over all items on each date, in date order (a date's items with an empty value are skipped).
  function totalsByDate(rows, col) {
    const m = new Map();
    for (const r of rows) {
      if (r[col] == null) continue;
      const t = m.get(r.date) || { date: r.date, total: 0, n: 0 };
      t.total += r[col]; t.n += 1; m.set(r.date, t);
    }
    return [...m.values()].sort((a, b) => (a.date < b.date ? -1 : 1));
  }

  // Change in the sum of `col` from the latest earlier date to the latest date, counting only the items that
  // have a value on both dates, so an item joining or leaving does not look like growth.
  function totalChange(rows, col) {
    const latest = latestDate(rows), earlier = dates(rows).filter(d => d < latest);
    if (!earlier.length) return null;
    const prev = earlier[earlier.length - 1];
    const before = new Map(onDate(rows, prev).filter(r => r[col] != null).map(r => [r.item_id, r[col]]));
    let was = 0, now = 0, n = 0;
    for (const r of onDate(rows, latest)) {
      if (r[col] == null || !before.has(r.item_id)) continue;
      was += before.get(r.item_id); now += r[col]; n += 1;
    }
    return { prev, latest, was, now, change: now - was, pct: pct(was, now), n };
  }

  const api = { NUM, parseCSV, dates, latestDate, onDate, seriesByItem, pct, moves, sinceFirst, biggestGains, median, spread,
                totalsByDate, totalChange, leaders };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Calc = api;
})(typeof window !== "undefined" ? window : globalThis);
