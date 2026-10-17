{% load static %}/* Kutubxona ilovasi — service worker.
   Vazifasi: statik fayllarni keshlash va internet yo'qolganda ogohlantirish.
   Sahifalar HAR DOIM avval tarmoqdan olinadi — eski ma'lumot ko'rsatilmasligi uchun. */

const CACHE = "kutubxona-v1";

const PRECACHE = [
  "{% static 'css/app.css' %}",
  "{% static 'img/icon-192.png' %}",
  "{% static 'img/icon-512.png' %}",
  "/offline/"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;

  // Faqat oddiy GET so'rovlar bilan ishlaymiz.
  // Test javoblari (POST) hech qachon keshlanmaydi.
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Admin bo'limi va maxfiy manzillarni umuman keshlamaymiz
  if (url.pathname.startsWith("/admin/") ||
      url.pathname.includes("/webhook/") ||
      url.pathname.includes("/cron/")) {
    return;
  }

  // Statik fayllar: avval keshdan (tez), keyin tarmoqdan
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          if (response && response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        });
      })
    );
    return;
  }

  // Sahifalar: avval tarmoqdan, ulanish bo'lmasa keshdan yoki offline sahifa
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match("/offline/")))
    );
  }
});
