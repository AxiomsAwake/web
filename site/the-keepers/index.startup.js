/** One campaign bootstrap. The generated Godot worker owns isolation and caching. */
export async function startWebCampaign({ config, policy, token }, platform = globalThis) {
  const scope = new URL('.', platform.location.href).href;
  const key = `keepers-web-isolation/v1:${scope}`;
  const notice = (text) => {
    const target = platform.document.getElementById('status-notice');
    if (target) target.textContent = text;
  };
  const bounded = (promise) => new Promise((resolve, reject) => {
    const timer = platform.setTimeout(() => reject(Error('Web startup deadline')), policy.activationTimeoutMs);
    Promise.resolve(promise).then(resolve, reject).finally(() => platform.clearTimeout(timer));
  });
  const isolated = () => platform.crossOriginIsolated === true &&
    typeof platform.SharedArrayBuffer === 'function';
  const loadEngine = (name) => new Promise((resolve, reject) => {
    const script = platform.document.createElement('script');
    script.src = name;
    script.onload = resolve;
    script.onerror = () => reject(Error('The game engine could not be downloaded.'));
    platform.document.head.append(script);
  });
  let storage;
  let attempted = true;
  try {
    storage = platform.sessionStorage;
    attempted = storage.getItem(key) === token;
    // Prove the reload guard is writable before considering any navigation.
    storage.setItem(key, token);
  } catch {
    storage = null;
  }
  let variant = 'single';
  try {
    if (!isolated() && storage && !attempted && platform.isSecureContext &&
        platform.navigator.serviceWorker) {
      notice('Preparing the game…');
      try {
        await bounded(platform.navigator.serviceWorker.register(config.serviceWorker));
        const registration = await bounded(platform.navigator.serviceWorker.ready);
        if (registration.scope !== scope || !registration.active) {
          throw Error('The game service worker has an unexpected scope.');
        }
        const workerURL = new URL(config.serviceWorker, scope).href;
        const controlled = () => platform.navigator.serviceWorker.controller?.scriptURL === workerURL;
        if (!controlled()) {
          let changed;
          try {
            await bounded(new Promise((resolve) => {
              changed = () => {
                if (controlled()) {
                  platform.navigator.serviceWorker.removeEventListener('controllerchange', changed);
                  resolve();
                }
              };
              platform.navigator.serviceWorker.addEventListener('controllerchange', changed);
              registration.active.postMessage('claim');
              changed();
            }));
          } finally {
            platform.navigator.serviceWorker.removeEventListener('controllerchange', changed);
          }
        }
        platform.location.reload();
        return { state: 'reloading' };
      } catch {
        // One failed/blocked isolation attempt uses the same campaign and Save scope.
      }
    }
    if (isolated()) {
      variant = 'threaded';
    }
    // Each generated engine declares global lexical names. Load exactly one.
    await loadEngine(variant === 'threaded' ? 'index.js' : 'index.single.js');
    const selected = variant === 'threaded' ? config : {
      ...config, executable: 'index.single', mainPack: 'index.pck', serviceWorker: '',
      ensureCrossOriginIsolationHeaders: false,
    };
    platform.keepersWebStartup = Object.freeze({ variant, scope });
    notice('Loading the game…');
    const engine = new platform.Engine(selected);
    await engine.startGame();
    notice('');
    const overlay = platform.document.getElementById('status');
    if (overlay) overlay.style.display = 'none';
    return { state: 'started', variant };
  } catch (error) {
    notice(error.message || 'The game could not start. Reload to try again.');
    return { state: 'failed', reason: error.message };
  }
}
