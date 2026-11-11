// Pure functions on the history rows. Shared by the pages and by tests/trends_check.js (Node),
// so the numbers on the Trends page can be checked against data/history.csv.
(function (root) {
  const NUM = ["subscribers", "views", "videos", "views_per_video", "videos_7d", "days_since_upload", "recent_avg_views"];

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
      for (const c of NUM) o[c] = o[c] === "" ? null : Number(o[c]);
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

  const api = { NUM, parseCSV, dates, latestDate, onDate, seriesByItem, pct, moves, sinceFirst, biggestGains, median, spread };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Calc = api;
})(typeof window !== "undefined" ? window : globalThis);
