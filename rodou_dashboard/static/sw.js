// Registrale-DOU — Service Worker Mínimo (PWA Lite)
// Este SW é o requisito técnico mínimo para habilitar a instalação como app.
// Não implementa cache offline porque o dashboard depende 100% do backend Flask.

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  event.respondWith(fetch(event.request));
});
