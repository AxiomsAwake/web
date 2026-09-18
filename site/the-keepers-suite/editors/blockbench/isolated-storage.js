/* Keep third-party editor settings/reset separate from other games on this origin. */
(() => {
  'use strict';
  for (const kind of ['localStorage', 'sessionStorage']) {
    const storage = window[kind], prefix = 'axioms:blockbench:';
    const keys = () => Array.from({ length: storage.length }, (_, i) => storage.key(i)).filter(k => k?.startsWith(prefix));
    const api = {
      getItem: key => storage.getItem(prefix + key),
      setItem: (key, value) => storage.setItem(prefix + key, String(value)),
      removeItem: key => storage.removeItem(prefix + key),
      clear: () => keys().forEach(key => storage.removeItem(key)),
      key: index => keys()[index]?.slice(prefix.length) ?? null,
      get length() { return keys().length; }
    };
    Object.defineProperty(window, kind, { configurable: false, value: new Proxy(api, {
      get(target, key) { return key in target ? target[key] : typeof key === 'string' ? target.getItem(key) : undefined; },
      set(target, key, value) { target.setItem(key, value); return true; },
      deleteProperty(target, key) { target.removeItem(key); return true; },
      ownKeys() { return keys().map(key => key.slice(prefix.length)); },
      getOwnPropertyDescriptor() { return { enumerable: true, configurable: true }; }
    }) });
  }
})();
