/* Home Meal Planner - service worker.
 *
 * Purpose: let "The Week" be read on a phone that is nowhere near the house.
 * Read-only by design. Nothing is queued for later; a write attempted offline
 * is refused up front by app.js rather than half-applied here.
 *
 * Three caching behaviours, chosen per request:
 *   shell (html/css/js/manifest/icons) - cache first, refreshed in background
 *   /images/...                        - cache first, kept forever (filenames
 *                                        carry a timestamp and never change)
 *   /api/data                          - network first with a short timeout,
 *                                        falling back to the last good copy
 *
 * Bump CACHE_VERSION on release: it is what evicts the old shell.
 */

var CACHE_VERSION = "mp-v21";
var SHELL_CACHE = CACHE_VERSION + "-shell";
var DATA_CACHE = CACHE_VERSION + "-data";
var IMAGE_CACHE = CACHE_VERSION + "-img";

/* The server is on the LAN. When the phone is elsewhere the request usually
   fails at once, but on a hotel or captive wifi it can hang instead - so race
   against a timer rather than trusting fetch to give up. */
var NETWORK_TIMEOUT = 3500;

/* The manifest and the icons are deliberately not in here. Both now carry the
   device's accent on the query string, which is part of the cache key, so
   precaching the bare URLs would only ever store a green copy nobody asks for.
   They are cached on demand instead, by the same cache-first rule - and an
   installed app already has its icon from the OS regardless. */
var SHELL = [
  "/",
  "/style.css",
  "/app.js"
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(SHELL_CACHE).then(function (cache) {
      /* addAll is all-or-nothing; one slow icon shouldn't fail the install. */
      return Promise.all(SHELL.map(function (url) {
        return cache.add(new Request(url, { cache: "reload" })).catch(function () {});
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (key) {
        if (key.indexOf(CACHE_VERSION) !== 0) return caches.delete(key);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

/* ------------------------------------------------------------------ helpers */

function timedFetch(request, ms) {
  return new Promise(function (resolve, reject) {
    var settled = false;
    var timer = setTimeout(function () {
      if (!settled) { settled = true; reject(new Error("timeout")); }
    }, ms);
    fetch(request).then(function (res) {
      if (settled) return;
      settled = true; clearTimeout(timer); resolve(res);
    }, function (err) {
      if (settled) return;
      settled = true; clearTimeout(timer); reject(err);
    });
  });
}

/* Re-issue a cached response with markers app.js can read, so the app knows to
   show the offline banner and disable editing. Response headers are immutable,
   hence the rebuild. */
function markOffline(response) {
  return response.blob().then(function (body) {
    var headers = new Headers();
    response.headers.forEach(function (v, k) { headers.set(k, v); });
    headers.set("X-Offline-Cache", "1");
    if (!headers.get("X-Cached-At")) headers.set("X-Cached-At", "");
    return new Response(body, {
      status: response.status,
      statusText: response.statusText,
      headers: headers
    });
  });
}

function storeData(cache, request, response) {
  var headers = new Headers();
  response.headers.forEach(function (v, k) { headers.set(k, v); });
  headers.set("X-Cached-At", new Date().toISOString());
  return response.blob().then(function (body) {
    cache.put(request, new Response(body, {
      status: response.status, statusText: response.statusText, headers: headers
    }));
  });
}

/* ------------------------------------------------------------------- routing */

self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method !== "GET") return;             // writes never go to cache

  var url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  /* The kitchen display and the design preview are always used at home on a
     device that stays put - leave them entirely alone. */
  if (url.pathname.indexOf("/kitchen") === 0 || url.pathname.indexOf("/preview") === 0) return;

  if (url.pathname === "/api/data") {
    event.respondWith(dataFirst(request,
      "No saved copy of the meal plan on this device yet."));
    return;
  }

  /* The shopping list is worked out by the server, so it can't be rebuilt on
     the phone - but a copy of the last answer is exactly what you want in your
     hand in the shop. Cached per week: the query string is part of the key. */
  if (url.pathname === "/api/shopping") {
    event.respondWith(dataFirst(request,
      "No saved copy of this week's shopping list on this device yet. " +
      "Open the Shopping tab once while you're at home."));
    return;
  }

  /* Everything else under /api is computed per request and has no sensible
     offline answer. Let it fail; app.js shows an offline message on those
     views. */
  if (url.pathname.indexOf("/api/") === 0) return;

  if (url.pathname.indexOf("/images/") === 0) {
    event.respondWith(cacheFirst(request, IMAGE_CACHE));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(navigation(request));
    return;
  }

  event.respondWith(cacheFirst(request, SHELL_CACHE));
});

/* Last known answer beats no answer. */
function dataFirst(request, emptyMessage) {
  return caches.open(DATA_CACHE).then(function (cache) {
    return timedFetch(request, NETWORK_TIMEOUT).then(function (response) {
      if (response && response.ok) storeData(cache, request, response.clone());
      return response;
    }).catch(function () {
      return cache.match(request).then(function (hit) {
        if (hit) return markOffline(hit);
        return new Response(
          JSON.stringify({ error: emptyMessage }),
          { status: 503, headers: { "Content-Type": "application/json", "X-Offline-Cache": "1" } }
        );
      });
    });
  });
}

/* Serve from cache immediately, then quietly refresh for next time. */
function cacheFirst(request, cacheName) {
  return caches.open(cacheName).then(function (cache) {
    return cache.match(request).then(function (hit) {
      var network = fetch(request).then(function (response) {
        if (response && response.ok) cache.put(request, response.clone());
        return response;
      }).catch(function () { return hit; });
      return hit || network;
    });
  });
}

function navigation(request) {
  return timedFetch(request, NETWORK_TIMEOUT).then(function (response) {
    if (response && response.ok) {
      /* Cloned here, synchronously: by the time caches.open resolves the body
         may already be streaming to the page, and it can only be read once. */
      var copy = response.clone();
      caches.open(SHELL_CACHE).then(function (c) { c.put("/", copy); });
    }
    return response;
  }).catch(function () {
    return caches.match("/", { cacheName: SHELL_CACHE }).then(function (hit) {
      return hit || caches.match("/");
    });
  });
}

/* app.js asks for this after a release so the new shell lands without the user
   having to close every tab. */
self.addEventListener("message", function (event) {
  if (event.data === "skip-waiting") self.skipWaiting();
});
