// Network first, so online visits always show the latest data; the cache is the offline fallback.
const CACHE = "finfluence-v5";
const SHELL = ["./", "index.html", "browse.html", "trends.html", "style.css?v=5", "app.js?v=5", "calc.js?v=5", "charts.js?v=5",
  "manifest.webmanifest", "icon.svg", "icon-192.png", "icon-512.png", "data/history.csv", "data/status.json"];

self.addEventListener("install", e => {
  // addAll fails as a whole if one file is missing (e.g. no data yet), so add the files one by one
  e.waitUntil(caches.open(CACHE).then(c => Promise.all(SHELL.map(f => c.add(f).catch(() => {})))));
  self.skipWaiting();
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  if (e.request.method !== "GET" || new URL(e.request.url).origin !== location.origin) return;
  e.respondWith(
    fetch(new Request(e.request, { cache: "no-cache" })).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); }
      return res;
    }).catch(() => caches.match(e.request).then(hit => hit ||
      (new URL(e.request.url).pathname.includes("/data/") ? Response.error() : caches.match("index.html"))))
  );
});
