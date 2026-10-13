/* Runs only inside a proxied WebUI iframe. Routes absolute application paths
   back into this WebUI's own AGMS namespace. */
(() => {
  const current = document.currentScript;
  if (!current) return;
  const prefix = current.dataset.prefix;
  const cookiePrefix = current.dataset.cookiePrefix;
  if (!prefix || !cookiePrefix) return;
  const upstream = current.dataset.upstream;
  function rewrite(input) {
    if (typeof input !== 'string') return input;
    if (input.startsWith(prefix + '/') || input === prefix) return input;
    if (input.startsWith('/') && !input.startsWith('//')) return prefix + input;
    if (upstream && (input === upstream || input.startsWith(upstream + '/'))) return prefix + input.slice(upstream.length);
    return input;
  }
  const fetchOriginal = window.fetch.bind(window);
  window.fetch = function(input, init) {
    if (typeof input === 'string') return fetchOriginal(rewrite(input), init);
    if (input instanceof URL) return fetchOriginal(rewrite(String(input)), init);
    if (input instanceof Request) {
      const url = rewrite(input.url);
      if (url !== input.url) return fetchOriginal(new Request(url, input), init);
    }
    return fetchOriginal(input, init);
  };
  const xhrOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    return xhrOpen.call(this, method, rewrite(String(url)), ...rest);
  };
  // Cookie names are namespaced server-side to prevent collisions between apps.
  // Expose the upstream names to JavaScript-based CSRF clients.
  try {
    const descriptor = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie');
    if (descriptor && descriptor.configurable) {
      Object.defineProperty(document, 'cookie', {
        configurable: true,
        get() {
          return descriptor.get.call(document).split('; ').filter(Boolean)
            .filter(v => v.startsWith(cookiePrefix))
            .map(v => v.slice(cookiePrefix.length)).join('; ');
        },
        set(value) {
          const idx = String(value).indexOf('=');
          if (idx < 1) return;
          descriptor.set.call(document, cookiePrefix + String(value).slice(0, idx) + String(value).slice(idx));
        }
      });
    }
  } catch (_) {}
})();
