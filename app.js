// Shared by all three pages: navigation bar, data loading, formatting helpers.
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = v => (v == null ? "–" : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString() : String(Math.round(v * 10) / 10));
const fmtPct = v => (v == null ? "–" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`);
const delta = v => (v == null ? "" : v === 0 ? "±0" : `${v > 0 ? "+" : "−"}${fmt(Math.abs(v))}`);

// "Nov 11, 15:28 UTC" for an ISO timestamp.
const fmtUTC = iso => new Date(iso).toLocaleString("en-US", { timeZone: "UTC", month: "short", day: "numeric",
  hour: "2-digit", minute: "2-digit", hour12: false }) + " UTC";

// "2026-11-11" as "Nov 11", or "November 11, 2026" when long.
const fmtDay = (d, long = false) => new Date(d + "T00:00:00Z").toLocaleDateString("en-US", long
  ? { timeZone: "UTC", month: "long", day: "numeric", year: "numeric" } : { timeZone: "UTC", month: "short", day: "numeric" });

// A small up/down badge for a change; `text` is what it says.
const pill = (v, text) => `<span class="pill ${v == null ? "flat" : v > 0 ? "up" : v < 0 ? "down" : "flat"}">` +
  `${v == null ? "" : v > 0 ? "▲ " : v < 0 ? "▼ " : ""}${text}</span>`;

// Three soft orbs behind every page (styled in style.css). --scroll runs from 0 at the top of the page to 1 at the
// bottom and moves them as the reader scrolls, on top of their slow drift.
function renderBackdrop() {
  document.body.insertAdjacentHTML("afterbegin", `<div class="orbs" aria-hidden="true"><i class="orb o1"></i><i class="orb o2"></i><i class="orb o3"></i></div>`);
  const root = document.documentElement.style;
  let queued = false;
  const update = () => {
    queued = false;
    const max = document.documentElement.scrollHeight - window.innerHeight;
    root.setProperty("--scroll", (max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0).toFixed(4));
  };
  window.addEventListener("scroll", () => { if (!queued) { queued = true; requestAnimationFrame(update); } }, { passive: true });
  window.addEventListener("resize", update);
  update();
}

function renderNav(active) {
  renderBackdrop();
  const links = [["index.html", "Today"], ["browse.html", "Browse"], ["trends.html", "Trends"]];
  document.body.insertAdjacentHTML("afterbegin",
    `<nav><span class="brand"><i class="mark"></i>Finfluence</span>` +
    links.map(([h, t]) => `<a href="${h}" class="${h === active ? "on" : ""}">${t}</a>`).join("") + `</nav>`);
}

// The service worker answers from its cache when the network is down, so this still works offline.
async function loadData() {
  const [csv, status] = await Promise.all([
    fetch("data/history.csv", { cache: "no-cache" }).then(r => { if (!r.ok) throw new Error("history.csv " + r.status); return r.text(); }),
    fetch("data/status.json", { cache: "no-cache" }).then(r => { if (!r.ok) throw new Error("status.json " + r.status); return r.json(); }),
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
