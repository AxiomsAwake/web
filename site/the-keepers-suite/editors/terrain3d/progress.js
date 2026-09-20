'use strict';
// A bounded lifecycle trace, independent of the editor and native project data.
(() => {
  const key = 'axioms-editor-progress:' + location.pathname;
  const start = performance.now(), events = [];
  let previous = '';
  function record(phase, detail = '') {
    const text = String(detail).slice(0, 1200);
    if (phase + text === previous) return;
    previous = phase + text;
    const event = {phase, detail: text, utc: new Date().toISOString(), ms: Math.round(performance.now() - start)};
    events.push(event); if (events.length > 40) events.shift();
    try { sessionStorage.setItem(key, JSON.stringify(events)); } catch (_) { /* diagnostics must not block editing */ }
    console.info('FULL_EDITOR_HANDOFF ' + JSON.stringify(event));
  }
  const status = document.getElementById('status'), error = document.getElementById('error');
  new MutationObserver(() => {
    if (error.style.display === 'block') record('rejected', error.textContent);
  }).observe(error, {childList: true, subtree: true, attributes: true});
  new MutationObserver(() => {
    const text = status.textContent;
    if (!text.startsWith('Loading native project:')) record('status', text);
  }).observe(status, {childList: true, subtree: true});
  for (const id of ['download', 'return', 'open', 'new']) {
    document.getElementById(id)?.addEventListener('click', () => record('request', id));
  }
  window.addEventListener('error', e => record('javascript-error', e.message));
  window.addEventListener('unhandledrejection', e => record('promise-error', e.reason?.message || e.reason));
  window.addEventListener('pagehide', () => record('pagehide'));
  window.AxiomsEditorProgress = Object.freeze({snapshot: () => events.slice(), record});
  record('host-start');
})();
