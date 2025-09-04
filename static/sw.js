// Second Brain Service Worker
// Provides offline functionality and caching for PWA

const CACHE_NAME = 'second-brain-v1';
const OFFLINE_URL = '/offline';

// Core files to cache for offline functionality
const CORE_CACHE_FILES = [
  '/',
  '/static/css/design-system.css',
  '/static/manifest.json',
  '/offline',
  '/static/brain-logo.svg'
];

// Cache strategies
const CACHE_FIRST_PATHS = [
  '/static/',
  '/favicon.ico'
];

const NETWORK_FIRST_PATHS = [
  '/api/',
  '/capture',
  '/search'
];

// Install event - cache core files
self.addEventListener('install', event => {
  console.log('[SW] Installing service worker...');
  
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('[SW] Caching core files');
        return cache.addAll(CORE_CACHE_FILES);
      })
      .then(() => {
        console.log('[SW] Core files cached successfully');
        // Force activation of new service worker
        return self.skipWaiting();
      })
      .catch(error => {
        console.error('[SW] Failed to cache core files:', error);
      })
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
  console.log('[SW] Activating service worker...');
  
  event.waitUntil(
    caches.keys()
      .then(cacheNames => {
        return Promise.all(
          cacheNames
            .filter(cacheName => cacheName !== CACHE_NAME)
            .map(cacheName => {
              console.log('[SW] Deleting old cache:', cacheName);
              return caches.delete(cacheName);
            })
        );
      })
      .then(() => {
        console.log('[SW] Service worker activated');
        // Take control of all pages immediately
        return self.clients.claim();
      })
  );
});

// Fetch event - handle network requests
self.addEventListener('fetch', event => {
  // Skip non-GET requests
  if (event.request.method !== 'GET') {
    return;
  }

  const url = new URL(event.request.url);
  
  // Skip external requests
  if (url.origin !== location.origin) {
    return;
  }

  // Handle different request types with appropriate strategies
  if (shouldUseCacheFirst(url.pathname)) {
    event.respondWith(cacheFirstStrategy(event.request));
  } else if (shouldUseNetworkFirst(url.pathname)) {
    event.respondWith(networkFirstStrategy(event.request));
  } else {
    event.respondWith(networkFirstWithFallback(event.request));
  }
});

// Cache first strategy (for static assets)
function cacheFirstStrategy(request) {
  return caches.match(request)
    .then(cachedResponse => {
      if (cachedResponse) {
        return cachedResponse;
      }
      
      return fetch(request)
        .then(response => {
          if (response.status === 200) {
            const responseClone = response.clone();
            caches.open(CACHE_NAME)
              .then(cache => cache.put(request, responseClone));
          }
          return response;
        });
    });
}

// Network first strategy (for API calls and dynamic content)
function networkFirstStrategy(request) {
  return fetch(request)
    .then(response => {
      if (response.status === 200) {
        const responseClone = response.clone();
        caches.open(CACHE_NAME)
          .then(cache => cache.put(request, responseClone));
      }
      return response;
    })
    .catch(() => {
      return caches.match(request);
    });
}

// Network first with offline fallback
function networkFirstWithFallback(request) {
  return fetch(request)
    .then(response => {
      if (response.status === 200) {
        const responseClone = response.clone();
        caches.open(CACHE_NAME)
          .then(cache => cache.put(request, responseClone));
      }
      return response;
    })
    .catch(() => {
      return caches.match(request)
        .then(cachedResponse => {
          if (cachedResponse) {
            return cachedResponse;
          }
          
          // Return offline page for navigation requests
          if (request.mode === 'navigate') {
            return caches.match(OFFLINE_URL);
          }
          
          throw new Error('No cached version available');
        });
    });
}

// Helper functions to determine caching strategy
function shouldUseCacheFirst(pathname) {
  return CACHE_FIRST_PATHS.some(path => pathname.startsWith(path));
}

function shouldUseNetworkFirst(pathname) {
  return NETWORK_FIRST_PATHS.some(path => pathname.startsWith(path));
}

// Handle background sync for offline note capture
self.addEventListener('sync', event => {
  console.log('[SW] Background sync triggered:', event.tag);
  
  if (event.tag === 'offline-note-sync') {
    event.waitUntil(syncOfflineNotes());
  }
});

// Sync offline notes when connection is restored
async function syncOfflineNotes() {
  try {
    const offlineNotes = await getOfflineNotes();
    
    for (const note of offlineNotes) {
      try {
        const response = await fetch('/capture', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(note)
        });
        
        if (response.ok) {
          await removeOfflineNote(note.id);
          console.log('[SW] Synced offline note:', note.id);
        }
      } catch (error) {
        console.error('[SW] Failed to sync note:', note.id, error);
      }
    }
  } catch (error) {
    console.error('[SW] Failed to sync offline notes:', error);
  }
}

// IndexedDB helpers for offline note storage
async function getOfflineNotes() {
  // Placeholder - would integrate with IndexedDB
  return [];
}

async function removeOfflineNote(noteId) {
  // Placeholder - would remove from IndexedDB
}

// Handle push notifications (future feature)
self.addEventListener('push', event => {
  if (event.data) {
    const data = event.data.json();
    
    event.waitUntil(
      self.registration.showNotification(data.title, {
        body: data.body,
        icon: '/static/icons/icon-192x192.png',
        badge: '/static/icons/badge-72x72.png',
        tag: data.tag || 'default',
        data: data.data
      })
    );
  }
});

// Handle notification click
self.addEventListener('notificationclick', event => {
  event.notification.close();
  
  event.waitUntil(
    clients.openWindow(event.notification.data?.url || '/')
  );
});

console.log('[SW] Service worker loaded successfully');