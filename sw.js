const CACHE_NAME = 'pg-app-v1';
// Elenco di tutti i file da salvare nella memoria del telefono
const ASSETS = [
  './',
  './index.html',
  './canti.js',
  './logo.png',
  './manifest.json'
];

// Installazione: scarica e salva i file in cache
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS);
    })
  );
});

// Attivazione: cancella vecchie versioni della cache se aggiorni l'app
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    })
  );
});

// Intercettazione richieste: serve i file dalla cache se manca internet
self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      // Restituisce il file in locale, altrimenti prova a scaricarlo dalla rete
      return cachedResponse || fetch(event.request);
    })
  );
});