'use strict';
// Opaque native projects, not a terrain model, replay engine or game validator.
window.AxiomsNativeMoments = function ({scope, databaseName = 'axioms-native-moments-v1',
  maxItems = 8, maxBytes = 128 * 1024 * 1024, maxProjectBytes = 64 * 1024 * 1024} = {}) {
  if (typeof scope !== 'string' || !scope || scope.length > 256 || /[\x00-\x1f]/.test(scope))
    throw new Error('A bounded project scope is required.');
  for (const [value, limit] of [[maxItems, 32], [maxBytes, 512 * 1024 * 1024], [maxProjectBytes, 512 * 1024 * 1024]])
    if (!Number.isSafeInteger(value) || value < 1 || value > limit) throw new Error('Invalid experiment shelf budget.');
  const range = () => IDBKeyRange.bound([scope, ''], [scope, '\uffff']);
  const sha = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
    value => value.toString(16).padStart(2, '0')).join('');
  function name(value) {
    if (typeof value !== 'string' || !value.trim() || value.trim().length > 64 || /[\x00-\x1f]/.test(value))
      throw new Error('Name this idea using 1–64 characters.');
    return value.trim();
  }
  function id(value) {
    if (typeof value !== 'string' || !/^[a-f0-9-]{36}$/.test(value)) throw new Error('Invalid moment identity.');
    return value;
  }
  function database() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(databaseName, 1);
      let settled = false;
      request.onupgradeneeded = () => {
        request.result.createObjectStore('cards');
        request.result.createObjectStore('projects');
      };
      request.onerror = () => { settled = true; reject(request.error); };
      request.onblocked = () => { settled = true; reject(new Error('Close the other experiment shelf tab and retry.')); };
      request.onsuccess = () => {
        const db = request.result;
        if (settled) { db.close(); return; }
        db.onversionchange = () => db.close();
        resolve(db);
      };
    });
  }
  async function transaction(mode, body) {
    const db = await database();
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(['cards', 'projects'], mode);
        let result, failure;
        const abort = error => { failure = error; tx.abort(); };
        tx.oncomplete = () => resolve(result);
        tx.onabort = () => reject(failure || tx.error || new Error('Experiment storage was canceled.'));
        tx.onerror = () => { /* The abort handler retains the original transaction failure. */ };
        try { body(tx, value => { result = value; }, abort); } catch (error) { abort(error); }
      });
    } finally { db.close(); }
  }
  async function list() {
    return transaction('readonly', (tx, done, abort) => {
      const request = tx.objectStore('cards').getAll(range(), maxItems + 1);
      request.onsuccess = () => {
        if (request.result.length > maxItems) return abort(new Error('Experiment shelf inventory exceeds its budget.'));
        done(request.result.sort((a, b) => b.createdAt - a.createdAt || a.id.localeCompare(b.id)));
      };
    });
  }
  function previewBytes(value) {
    if (value == null) return null;
    if (!(value instanceof Uint8Array) || value.length < 33 || value.length > 1024 * 1024 ||
        ![137,80,78,71,13,10,26,10].every((byte, index) => value[index] === byte) ||
        ![73,72,68,82].every((byte, index) => value[index + 12] === byte))
      throw new Error('The saved preview must be a bounded PNG.');
    const view = new DataView(value.buffer, value.byteOffset, value.byteLength);
    if (view.getUint32(16) < 1 || view.getUint32(20) < 1 || view.getUint32(16) > 2048 || view.getUint32(20) > 2048)
      throw new Error('Saved preview dimensions exceed the shelf budget.');
    return value.slice();
  }
  async function keep(label, snapshot) {
    label = name(label);
    if (!(snapshot?.bytes instanceof Uint8Array) || !snapshot.bytes.length || snapshot.bytes.length > maxProjectBytes)
      throw new Error('This native project is too large for the shelf. Keep its native download instead.');
    if (typeof snapshot.format !== 'string' || !/^[a-z0-9][a-z0-9._/-]{0,63}$/.test(snapshot.format))
      throw new Error('A native project format is required.');
    // Copy before asynchronous hashing so a caller cannot mutate admitted bytes.
    const bytes = snapshot.bytes.slice(), preview = previewBytes(snapshot.preview);
    const receipt = snapshot.receipt == null ? null : structuredClone(snapshot.receipt);
    if (receipt !== null && (typeof receipt !== 'object' || Array.isArray(receipt) || JSON.stringify(receipt).length > 16384))
      throw new Error('Native project receipt exceeds its budget.');
    const digest = await sha(bytes);
    if (receipt?.sha256 && receipt.sha256 !== digest) throw new Error('Native project receipt does not match its bytes.');
    const card = {schema: 1, id: crypto.randomUUID(), name: label, format: snapshot.format,
      sha256: digest, bytes: bytes.length, storedBytes: bytes.length + (preview?.length || 0),
      createdAt: Date.now(), preview, receipt};
    return transaction('readwrite', (tx, done, abort) => {
      const cards = tx.objectStore('cards'), request = cards.getAll(range(), maxItems + 1);
      request.onsuccess = () => {
        try {
          const existing = request.result;
          const duplicate = existing.find(item => item.sha256 === digest && item.format === card.format);
          if (duplicate) { done({card: duplicate, duplicate: true}); return; }
          const used = existing.reduce((sum, item) => {
            if (!Number.isSafeInteger(item.storedBytes) || item.storedBytes < 1) throw new Error('Invalid shelf inventory.');
            return sum + item.storedBytes;
          }, 0);
          if (existing.length >= maxItems || used + card.storedBytes > maxBytes)
            throw new Error('The experiment shelf is full. Download and remove a moment before keeping another; nothing was evicted.');
          const key = [scope, card.id];
          cards.add(card, key); tx.objectStore('projects').add(bytes, key);
          done({card, duplicate: false});
        } catch (error) { abort(error); }
      };
    });
  }
  async function read(momentId) {
    const key = [scope, id(momentId)];
    const result = await transaction('readonly', (tx, done) => {
      const result = {};
      tx.objectStore('cards').get(key).onsuccess = event => { result.card = event.target.result; };
      tx.objectStore('projects').get(key).onsuccess = event => { result.bytes = event.target.result; };
      done(result);
    });
    if (!result.card || !(result.bytes instanceof Uint8Array)) throw new Error('This moment is unavailable in this project scope.');
    if (result.bytes.length !== result.card.bytes || await sha(result.bytes) !== result.card.sha256)
      throw new Error('This saved moment failed byte verification. The open project is unchanged.');
    return {...result.card, bytes: result.bytes};
  }
  async function remove(momentId) {
    const key = [scope, id(momentId)];
    await transaction('readwrite', tx => {
      tx.objectStore('cards').delete(key); tx.objectStore('projects').delete(key);
    });
  }
  return Object.freeze({list, keep, read, remove, validateName: name,
    limits: Object.freeze({maxItems, maxBytes, maxProjectBytes})});
};
