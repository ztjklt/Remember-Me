// Network-only worker: never cache authenticated stories, original audio or API
// answers. New HTML/assets are revalidated by the server on the next navigation.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  if(event.request.mode==='navigate') event.respondWith(fetch(event.request).catch(() => new Response('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>勿忘我 · 暂时离线</title><h1>暂时没有网络</h1><p>连接网络后重新打开，就能继续阅读故事。</p><a href="/workbench/">重新连接</a></html>', {status:503,headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'}})));
});
