const CACHE = 'skybrief-shell-v1';
self.addEventListener('install', event => { self.skipWaiting(); event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(['/','/index.html']))); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('skybrief-shell-') && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin || new URL(req.url).pathname.startsWith('/api/')) return;
  if (req.mode === 'navigate') { event.respondWith(fetch(req).catch(() => caches.match('/index.html'))); return; }
  event.respondWith(caches.match(req).then(cached => cached || fetch(req).then(response => {
    if (response.ok && (req.destination === 'script' || req.destination === 'style' || req.destination === 'font' || req.destination === 'image')) {
      const copy = response.clone(); void caches.open(CACHE).then(cache => cache.put(req, copy));
    }
    return response;
  })));
});
