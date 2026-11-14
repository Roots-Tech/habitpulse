const CACHE_NAME = 'habitpulse-pwa-v5';
const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/offline/',
  '/static/css/style.css?v=20261110_mobile_v2',
  '/static/js/app.js?v=20261110_mobile_v2',
  '/static/images/habit_icon.png',
  '/static/images/pwa_icon_192.png',
  '/static/images/pwa_icon_512.png',
  '/static/images/pwa_icon_maskable.png',
  '/static/images/apple_touch_icon.png'
];

// 1. Install Event: Cache Core App Shell & Offline Assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('[ServiceWorker] Some assets could not be cached on install:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

// 2. Activate Event: Clean up outdated caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            console.log('[ServiceWorker] Removing old cache version:', key);
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// 3. Fetch Event: Network-first for HTML pages, Stale-while-revalidate for static assets
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') {
    return;
  }

  const url = new URL(event.request.url);

  // HTML navigation requests: network-only to prevent caching authenticated tenant data (PWA-01),
  // falling back cleanly to cached /offline/ page only when network drops.
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => {
        return caches.match('/offline/').then((offline) => {
          return offline || new Response('<h1>HabitPulse is currently offline.</h1>', {
            headers: { 'Content-Type': 'text/html' }
          });
        });
      })
    );
    return;
  }

  // Same-origin static assets
  if (url.origin === location.origin) {
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        if (cachedResponse) {
          // Update cache in background
          fetch(event.request).then((networkResponse) => {
            if (networkResponse && networkResponse.status === 200) {
              caches.open(CACHE_NAME).then((cache) => cache.put(event.request, networkResponse));
            }
          }).catch(() => {});
          return cachedResponse;
        }

        return fetch(event.request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const copy = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          }
          return networkResponse;
        });
      })
    );
  }
});

// 4. Push Notification Event: Receive free Web Push payload and display notification
self.addEventListener('push', (event) => {
  let data = {
    title: '⏰ HabitPulse Habit Alarm',
    body: 'Time to check in on your habits and keep your streak alive!',
    icon: '/static/images/pwa_icon_192.png',
    badge: '/static/images/habit_icon.png',
    habit_id: null,
    url: '/habits/'
  };

  if (event.data) {
    try {
      const parsed = event.data.json();
      data = Object.assign(data, parsed);
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: data.icon || '/static/images/pwa_icon_192.png',
    badge: data.badge || '/static/images/habit_icon.png',
    tag: `habit-alarm-${data.habit_id || 'general'}`,
    renotify: true,
    requireInteraction: true,
    vibrate: [250, 100, 250, 100, 250],
    data: {
      url: data.url || '/habits/',
      habit_id: data.habit_id
    },
    actions: [
      { action: 'complete', title: '✅ Mark Done' },
      { action: 'snooze', title: '⏳ Snooze 1h' }
    ]
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// 5. Notification Click Event: Handle "Mark Done", "Snooze 1h", or direct open
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const habitId = event.notification.data ? event.notification.data.habit_id : null;
  const targetUrl = (event.notification.data && event.notification.data.url) || '/habits/';

  if (event.action === 'complete' && habitId) {
    event.waitUntil(
      fetch(`/api/v1/habits/${habitId}/complete/`, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      }).then(() => {
        return clients.matchAll({ type: 'window' }).then((clientList) => {
          for (const client of clientList) {
            if (client.url && 'focus' in client) {
              client.postMessage({ type: 'HABIT_COMPLETED', habit_id: habitId });
              return client.focus();
            }
          }
        });
      })
    );
  } else if (event.action === 'snooze' && habitId) {
    event.waitUntil(
      fetch(`/api/v1/habits/${habitId}/reminder/snooze/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({ minutes: 60 })
      })
    );
  } else {
    // Open or focus application window
    event.waitUntil(
      clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
        for (const client of clientList) {
          if (client.url.includes('/habits/') && 'focus' in client) {
            return client.focus();
          }
        }
        if (clients.openWindow) {
          return clients.openWindow(targetUrl);
        }
      })
    );
  }
});
