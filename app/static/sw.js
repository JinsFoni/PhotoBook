/* PhotoBook service worker — PWA 可安装 + 离线兜底。
 * 策略刻意保守: 站点是登录后才能用的私相册, 图片/页面都是动态且随登录态变化,
 * 一律 network-only, 只缓存两类东西:
 *   1) 同源静态骨架 (/static/…, 版本化 query 由 ASSET_VER 保证更新)
 *   2) 导航请求失败时的离线兜底页 (从 cache 取, 不发网络)
 * 登录态由 Cookie 承载, fetch透传自然带上, 不做任何鉴权判断。 */

var VERSION = "pb-sw-v1";
var OFFLINE_URL = "/static/offline.html";

/* 预缓存: 离线兜底页 + 图标(manifest 引用, 装完即要展示) */
var PRECACHE = [
  OFFLINE_URL,
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/icon-maskable-512.png",
];

self.addEventListener("install", function (e) {
  e.waitUntil(
    caches.open(VERSION).then(function (c) { return c.addAll(PRECACHE); })
  );
  self.skipWaiting();
});

self.addEventListener("activate", function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        return k === VERSION ? null : caches.delete(k);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  /* 导航请求: network-first, 失败落离线兜底页 */
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req).catch(function () {
        return caches.match(OFFLINE_URL);
      })
    );
    return;
  }

  /* 同源静态: cache-first(带版本号, 命中即最新), 未命中回网络并顺手入缓存 */
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(
      caches.match(req).then(function (hit) {
        if (hit) return hit;
        return fetch(req).then(function (resp) {
          if (resp.ok && resp.type === "basic") {
            var copy = resp.clone();
            caches.open(VERSION).then(function (c) { c.put(req, copy); });
          }
          return resp;
        });
      })
    );
  }
  /* 其余(/media /t/ /api 页面本身)全部直连, 不拦截 */
});
