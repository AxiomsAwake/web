'use strict';
// Reuse Godot's own service worker. Never change another sub-site's worker/cache.
window.AxiomsEditorIsolation = async function(worker = 'service.worker.js') {
  if (crossOriginIsolated) return;
  if (!isSecureContext || !navigator.serviceWorker) throw new Error('The full editor needs HTTPS and service-worker support. Open the same native project in Godot on Windows or Linux when these are unavailable.');
  const workerURL = new URL(worker, location.href);
  if (workerURL.origin !== location.origin) throw new Error('Editor worker must remain in the application origin');
  const registration = await navigator.serviceWorker.register(workerURL, {scope: new URL('.', workerURL).pathname, updateViaCache: 'none'});
  await new Promise((resolve, reject) => {
    const candidate = registration.installing || registration.waiting || registration.active;
    if (!candidate) { reject(new Error('The editor isolation worker was not created')); return; }
    if (candidate.state === 'activated') { resolve(); return; }
    const timeout = setTimeout(() => reject(new Error('Editor worker activation timed out; the current project is unchanged')), 30000);
    candidate.addEventListener('statechange', () => {
      if (candidate.state === 'activated') { clearTimeout(timeout); resolve(); }
      else if (candidate.state === 'redundant') { clearTimeout(timeout); reject(new Error('Editor worker installation failed')); }
    });
    if (candidate.state === 'installed') candidate.postMessage('claim');
  });
  registration.active.postMessage('claim');
  const marker = 'axioms-editor-isolation:' + workerURL.pathname;
  const attempts = Number(sessionStorage.getItem(marker) || '0');
  if (attempts >= 2) throw new Error('This page is still not cross-origin isolated. Open the editor as a top-level tab or use the native project; no editor features have been removed.');
  sessionStorage.setItem(marker, String(attempts + 1));
  if (!navigator.serviceWorker.controller) {
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('The editor worker could not claim this page')), 10000);
      navigator.serviceWorker.addEventListener('controllerchange', () => { clearTimeout(timeout); resolve(); }, {once: true});
    });
  }
  location.reload();
  await new Promise(() => {});
};
