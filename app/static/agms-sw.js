// Cache only public versioned static assets. Never cache authenticated pages or API responses.
const CACHE='agms-static-v1';
self.addEventListener('install',event=>{self.skipWaiting()});
self.addEventListener('activate',event=>{event.waitUntil(self.clients.claim())});
self.addEventListener('fetch',event=>{
 const request=event.request,url=new URL(request.url);
 if(request.method!=='GET'||url.origin!==self.location.origin||!url.pathname.startsWith('/static/'))return;
 if(!/\.(?:css|js|svg|webmanifest)$/.test(url.pathname))return;
 event.respondWith(fetch(request).then(response=>response).catch(()=>caches.match(request)));
});
