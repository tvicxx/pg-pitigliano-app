const CACHE_NAME = 'pg-app-v3';
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
  self.skipWaiting(); // la nuova versione (senza il vecchio widget) parte subito
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
    }).then(() => self.clients.claim())
  );
});

// Intercettazione richieste: serve i file dalla cache se manca internet
self.addEventListener('fetch', (event) => {
  // liturgia.json cambia ogni giorno: prima la rete (dato fresco),
  // se manca internet l'ultima copia salvata.
  if (new URL(event.request.url).pathname.endsWith('/liturgia.json')) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          }
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      // Restituisce il file in locale, altrimenti prova a scaricarlo dalla rete
      return cachedResponse || fetch(event.request);
    })
  );
});