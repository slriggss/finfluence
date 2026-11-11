// Tiny inline-SVG charts (no external library, so they also work offline).
const SVG_W = 720, SVG_H = 300, PAD = { l: 62, r: 14, t: 12, b: 78 };
const PALETTE = ["#8a2f5b", "#c27c2c", "#2f6f8a", "#4f8a2f", "#7a4fb3", "#b3402f", "#2f8a7a", "#8a7a2f",
  "#d06a9a", "#3a5fc0", "#9a5a2a", "#1f9a5a", "#b0307a", "#6a6a2a", "#2a9aa0", "#777777"];

// Nice axis: step is 1, 2 or 5 times a power of ten. zero=true forces the axis to include 0.
function niceScale(min, max, zero = true, ticks = 4) {
  if (zero) { min = Math.min(min, 0); max = Math.max(max, 0); }
  if (max === min) { max = min + 1; }
  const raw = (max - min) / ticks, p = 10 ** Math.floor(Math.log10(raw)), f = raw / p;
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
  return { lo: Math.floor(min / step) * step, hi: Math.ceil(max / step) * step, step };
}

const tick = v => (Math.abs(v) >= 1000 ? Math.round(v).toLocaleString() : String(Math.round(v * 100) / 100));

function frame(sc) {
  let s = "";
  const n = Math.round((sc.hi - sc.lo) / sc.step);
  for (let i = 0; i <= n; i++) {
    const v = sc.lo + i * sc.step, y = PAD.t + (SVG_H - PAD.t - PAD.b) * (1 - (v - sc.lo) / (sc.hi - sc.lo));
    s += `<line x1="${PAD.l}" x2="${SVG_W - PAD.r}" y1="${y}" y2="${y}" stroke="var(--line)"/>` +
         `<text x="${PAD.l - 6}" y="${y + 4}" text-anchor="end">${tick(v)}</text>`;
  }
  return s;
}

// series: [{name, color, values}] sharing one list of labels; null values leave a gap.
function lineChart(el, labels, series, zero = false) {
  const all = series.flatMap(s => s.values).filter(v => v != null);
  if (!all.length) { el.innerHTML = `<p class="empty">Nothing to show.</p>`; return; }
  const sc = niceScale(Math.min(...all), Math.max(...all), zero), n = labels.length;
  const x = i => PAD.l + (n === 1 ? (SVG_W - PAD.l - PAD.r) / 2 : (i * (SVG_W - PAD.l - PAD.r)) / (n - 1));
  const y = v => PAD.t + (SVG_H - PAD.t - PAD.b) * (1 - (v - sc.lo) / (sc.hi - sc.lo));
  let s = frame(sc);
  const step = Math.max(1, Math.ceil(n / 8));
  labels.forEach((l, i) => { if (i % step === 0 || i === n - 1) s += `<text x="${x(i)}" y="${SVG_H - PAD.b + 16}" text-anchor="middle">${l.slice(5)}</text>`; });
  series.forEach(se => {
    const pts = se.values.map((v, i) => (v == null ? null : [x(i), y(v)])).filter(Boolean);
    if (pts.length > 1) s += `<polyline fill="none" stroke="${se.color}" stroke-width="2.2" points="${pts.map(p => p.join(",")).join(" ")}"/>`;
    se.values.forEach((v, i) => { if (v != null) s += `<circle cx="${x(i)}" cy="${y(v)}" r="3.2" fill="${se.color}"><title>${labels[i]} · ${se.name}: ${tick(v)}</title></circle>`; });
  });
  el.innerHTML = `<svg viewBox="0 0 ${SVG_W} ${SVG_H}" role="img" width="100%">${s}</svg>`;
}

// A small trend line with no axes, for table cells and dashboard tiles. values run oldest to newest; empty ones are skipped.
function sparkline(values, w = 90, h = 26) {
  const v = values.filter(x => x != null);
  if (v.length < 2) return `<span class="muted">–</span>`;
  const lo = Math.min(...v), span = Math.max(...v) - lo, n = v.length;
  const x = i => 3 + (i * (w - 6)) / (n - 1), y = val => (span ? h - 3 - ((val - lo) / span) * (h - 6) : h / 2);
  const pts = v.map((val, i) => `${x(i).toFixed(1)},${y(val).toFixed(1)}`).join(" ");
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="trend over ${n} days">` +
    `<polyline fill="none" stroke="var(--accent)" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" points="${pts}"/>` +
    `<circle cx="${x(n - 1).toFixed(1)}" cy="${y(v[n - 1]).toFixed(1)}" r="2.6" fill="var(--accent)"/></svg>`;
}

// Vertical bars (negative values hang below zero). `unit` is appended in the tooltip.
function barChart(el, labels, values, unit = "") {
  if (!values.length) { el.innerHTML = `<p class="empty">Nothing to show.</p>`; return; }
  const sc = niceScale(Math.min(...values), Math.max(...values)), n = labels.length;
  const w = (SVG_W - PAD.l - PAD.r) / n, y = v => PAD.t + (SVG_H - PAD.t - PAD.b) * (1 - (v - sc.lo) / (sc.hi - sc.lo));
  let s = frame(sc);
  labels.forEach((l, i) => {
    const bx = PAD.l + i * w + w * 0.15, top = Math.min(y(values[i]), y(0)), h = Math.abs(y(values[i]) - y(0));
    s += `<rect x="${bx}" y="${top}" width="${w * 0.7}" height="${Math.max(h, 1)}" fill="${values[i] < 0 ? "var(--bad)" : "var(--accent)"}"><title>${esc(l)}: ${tick(values[i])}${unit}</title></rect>`;
    const short = l.length > 16 ? l.slice(0, 15) + "…" : l, lx = bx + w * 0.35, ly = SVG_H - PAD.b + 14;
    s += `<text x="${lx}" y="${ly}" text-anchor="end" transform="rotate(-40 ${lx} ${ly})">${esc(short)}</text>`;
  });
  el.innerHTML = `<svg viewBox="0 0 ${SVG_W} ${SVG_H}" role="img" width="100%">${s}</svg>`;
}
