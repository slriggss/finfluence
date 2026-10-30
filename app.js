// Shared by all three pages: navigation bar, data loading, formatting helpers.
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = v => (v == null ? "–" : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString() : String(Math.round(v * 10) / 10));
const fmtPct = v => (v == null ? "–" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`);
const delta = v => (v == null ? "" : v === 0 ? "±0" : `${v > 0 ? "+" : "−"}${fmt(Math.abs(v))}`);

function renderNav(active) {
  const links = [["index.html", "Today"], ["browse.html", "Browse"], ["trends.html", "Trends"]];
  document.body.insertAdjacentHTML("afterbegin",
    `<nav><span class="brand">Finfluence</span>` +
    links.map(([h, t]) => `<a href="${h}" class="${h === active ? "on" : ""}">${t}</a>`).join("") + `</nav>`);
}

// The service worker answers from its cache when the network is down, so this still works offline.
async function loadData() {
  const [csv, status] = await Promise.all([
    fetch("data/history.csv").then(r => { if (!r.ok) throw new Error("history.csv " + r.status); return r.text(); }),
    fetch("data/status.json").then(r => { if (!r.ok) throw new Error("status.json " + r.status); return r.json(); }),
  ]);
  const rows = Calc.parseCSV(csv);
  return { rows, status, latest: Calc.latestDate(rows) };
}

// Latest rows with each item's change since its previous row.
function latestWithChange(rows) {
  const latest = Calc.latestDate(rows), prev = new Map();
  for (const r of rows) if (r.date < latest) prev.set(r.item_id, r);  // rows are sorted, so the last one wins
  return Calc.onDate(rows, latest).map(r => {
    const p = prev.get(r.item_id), d = c => (p && p[c] != null && r[c] != null ? r[c] - p[c] : null);
    return { ...r, d_subscribers: d("subscribers"), d_views: d("views"), d_videos: d("videos"),
             pct_views: p ? Calc.pct(p.views, r.views) : null };
  });
}

function showError(e) {
  $("main").innerHTML = `<p class="empty">Could not load the data (${esc(e.message)}). Try again when online.</p>`;
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
