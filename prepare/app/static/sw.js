// Prepare service worker: network first, fall back to the last saved copy.
// Core pages are saved on install and refreshed every time they load online,
// so the phone always has the latest plan, contacts and pack for a power cut.
const CACHE = "prepare-v6";
const CORE = ["/", "/print", "/scan", "/static/scan.js", "/static/vendor/zxing-library-0.21.3.min.js", "/plans", "/contacts", "/meds", "/items", "/kit", "/household",
              "/offline", "/static/style.css", "/manifest.webmanifest", "/static/icon-192.png",
              "/static/fonts/barlow-condensed-latin-700-normal.woff2", "/static/fonts/barlow-condensed-latin-800-normal.woff2"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(CORE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET" || new URL(req.url).origin !== self.location.origin) return;
  const path = new URL(req.url).pathname;
  // Never keep API answers or backups (a whole copy of the household's data) in the cache.
  if (path.startsWith("/api/") || path.startsWith("/backup")) return;
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() =>
        caches.match(req, { ignoreSearch: false })
          .then((hit) => hit || caches.match(new URL(req.url).pathname))
          .then((hit) => hit || (req.mode === "navigate" ? caches.match("/offline") : Response.error()))
      )
  );
});

// After any save, pages re-fetch online, so the cache keeps itself current.
// Ask for a full refresh of the core pages (e.g. from the dashboard) with postMessage("refresh").
self.addEventListener("message", (event) => {
  if (event.data === "refresh") {
    event.waitUntil(caches.open(CACHE).then((c) => c.addAll(CORE)));
  }
});
