/* Startup transport only. Godot owns JSON admission and authoritative policy. */
(function install(host) {
  'use strict';
  const limit = 8192;
  async function readPolicy() {
    const controller = new AbortController();
    const deadline = setTimeout(() => controller.abort(), 5000);
    let reader;
    try {
      const url = new URL('./opponent-production.json', document.baseURI);
      const response = await fetch(url, {
        cache: 'no-store', credentials: 'omit', mode: 'same-origin',
        redirect: 'error', signal: controller.signal,
      });
      if (!response.ok) return { state: 'unavailable', reason: 'http_' + response.status };
      if (Number(response.headers.get('Content-Length')) > limit) {
        return { state: 'unavailable', reason: 'size_limit' };
      }
      reader = response.body.getReader();
      const chunks = [];
      let total = 0;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        total += value.byteLength;
        if (total > limit) return { state: 'unavailable', reason: 'size_limit' };
        chunks.push(value);
      }
      const bytes = new Uint8Array(total);
      let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
      return { state: 'loaded', text: new TextDecoder('utf-8', { fatal: true }).decode(bytes) };
    } catch (error) {
      return { state: 'unavailable', reason: controller.signal.aborted ? 'deadline' : 'transport_or_encoding' };
    } finally {
      if (reader) { try { await reader.cancel(); } catch (_) { /* Preserve the original result. */ } }
      clearTimeout(deadline);
    }
  }
  host.keepersStartGame = async function keepersStartGame(engine, options) {
    host.KeepersExternalProduction = Object.freeze(await readPolicy());
    // Even an unavailable replacement starts with the admitted bundled fallback;
    // the native player reports rejection instead of pretending it loaded.
    return engine.startGame(options);
  };
})(globalThis);
