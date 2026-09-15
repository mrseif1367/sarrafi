/* Service Worker — صرافی (PWA)
   استراتژی: cache-first برای فایل‌های استاتیک، network-first برای ناوبری
*/
const CACHE_NAME = 'sarrafi-v3';

const PRECACHE = [
  '/',
  '/static/index.html',
  '/static/css/style.css',
  '/static/vendor/DatePicker.css',
  '/static/vendor/DatePicker.js',
  '/static/js/charts.js',
  '/static/js/app.js',
  '/static/manifest.json',
  '/static/img/logo.svg',
  '/static/img/icons/icon-192.png',
  '/static/img/icons/icon-512.png',
  '/static/fonts/Vazirmatn-Regular.woff2',
  '/static/fonts/Vazirmatn-Medium.woff2',
  '/static/fonts/Vazirmatn-SemiBold.woff2',
  '/static/fonts/Vazirmatn-Bold.woff2'
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(PRECACHE);
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        if (k !== CACHE_NAME) return caches.delete(k);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (event) {
  var url = new URL(event.request.url);
  // فقط هم‌ریشه
  if (url.origin !== location.origin) return;
  // APIها همیشه از شبکه
  if (url.pathname.startsWith('/api/')) return;

  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(function () {
        return caches.match('/static/index.html');
      })
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then(function (cached) {
      var fetched = fetch(event.request).then(function (res) {
        if (res && res.status === 200) {
          var clone = res.clone();
          caches.open(CACHE_NAME).then(function (cache) { cache.put(event.request, clone); });
        }
        return res;
      }).catch(function () { return cached; });
      return cached || fetched;
    })
  );
});
