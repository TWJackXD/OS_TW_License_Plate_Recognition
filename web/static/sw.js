/* Network-first PWA shell — prefer fresh assets over stale cache. */
const CACHE = "violation-pwa-v4";
const PRECACHE = [
  "/",
  "/admin",
  "/static/style.css?v=20260730d",
  "/static/app.js?v=20260730d",
  "/static/capture.js?v=20260730d",
  "/static/admin.js?v=20260730d",
  "/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(PRECACHE).catch(() => undefined))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.map((k) => (k === CACHE ? null : caches.delete(k)))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/media/")) {
    return;
  }

  // HTML + CSS/JS: network-first so phones always try latest
  const isNavigate =
    req.mode === "navigate" || (req.headers.get("accept") || "").includes("text/html");
  const isAsset =
    url.pathname.startsWith("/static/") ||
    url.pathname === "/sw.js" ||
    url.pathname === "/manifest.webmanifest";

  if (isNavigate || isAsset) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req).then((r) => r || caches.match("/")))
    );
  }
});
