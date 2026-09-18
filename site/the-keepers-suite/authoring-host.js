/* Shared browser file transport and editor host. No game rules or remote service. */
(() => {
  'use strict';
  const MAX = 64 * 1024 * 1024;
  const PROTOCOL = 'axioms-authoring/v1';
  const picks = new Map();
  const state = Object.create(null);
  let editor = null;
  const safeName = value => String(value).split(/[\\/]/).pop().slice(0, 160) || 'asset';
  function report(scope, json) {
    if (!/^[a-z-]{1,32}$/.test(scope) || json.length > 32768) return;
    try {
      const value = JSON.parse(json);
      state[scope] = Object.freeze(value);
      window.dispatchEvent(new CustomEvent('axioms-authoring-status', { detail: { scope, value } }));
    } catch { /* A diagnostic never mutates an artifact. */ }
  }
  function cancelPick(id) {
    const pick = picks.get(id);
    if (pick) { pick.cancelled = true; pick.input.remove(); picks.delete(id); }
  }
  function pick(accept, maxBytes, id, callback) {
    if (typeof callback !== 'function' || !Number.isInteger(maxBytes) || maxBytes < 1 || maxBytes > MAX) return;
    cancelPick(id);
    const input = document.createElement('input');
    input.type = 'file'; input.accept = accept; input.hidden = true;
    input.dataset.axiomsFile = id;
    const pending = { input, cancelled: false };
    picks.set(id, pending); document.body.append(input);
    const finish = (status, name, data = null) => {
      if (pending.cancelled || picks.get(id) !== pending) return;
      cancelPick(id); callback(id, status, name, data);
    };
    input.addEventListener('cancel', () => finish('cancelled', 'File selection cancelled.'), { once: true });
    input.addEventListener('change', async () => {
      try {
        const file = input.files[0];
        if (!file) return finish('cancelled', 'File selection cancelled.');
        if (file.size < 1 || file.size > maxBytes) return finish('error', 'File exceeds the import limit or is empty.');
        const bytes = await file.arrayBuffer();
        finish('ok', safeName(file.name), bytes);
      } catch (error) { finish('error', `Could not read file: ${error.message}`); }
    }, { once: true });
    input.click();
  }
  function send(type) {
    if (editor?.ready) editor.frame.contentWindow.postMessage({ protocol: PROTOCOL, type, token: editor.token,
      context: editor.context }, location.origin);
  }
  function makeButton(text, action) {
    const button = document.createElement('button'); button.type = 'button'; button.textContent = text;
    button.style.cssText = 'padding:10px 16px;border:1px solid #789;background:#203746;color:white;border-radius:5px;cursor:pointer';
    button.addEventListener('click', action); return button;
  }
  function closeEditor(context) {
    if (!editor || editor.context !== context) return;
    clearTimeout(editor.timer); editor.dialog.close(); editor.dialog.remove(); editor = null;
  }
  function openEditor(entry, label, context, filename, source, callback) {
    if (typeof callback !== 'function' || typeof source !== 'string' || new TextEncoder().encode(source).length > MAX) return;
    const url = new URL(entry, document.baseURI);
    const base = new URL('editors/', document.baseURI);
    if (url.origin !== location.origin || !url.pathname.startsWith(base.pathname) || url.search || url.hash) {
      callback(context, 'error', 'Editor entry must be a bundled same-origin tool.', null, ''); return;
    }
    if (editor?.context === context) { editor.callback = callback; editor.dialog.showModal(); return; }
    if (editor) closeEditor(editor.context);
    const dialog = document.createElement('dialog');
    dialog.id = 'axioms-editor-dialog'; dialog.setAttribute('aria-label', `Model editor: ${label}`);
    dialog.style.cssText = 'position:fixed;inset:0;margin:auto;padding:0;border:1px solid #678;background:#151b22;color:#fff;width:98vw;height:96vh;max-width:none;max-height:none;overflow:hidden';
    const toolbar = document.createElement('div');
    toolbar.style.cssText = 'height:52px;box-sizing:border-box;display:flex;gap:10px;align-items:center;padding:6px 10px';
    const title = document.createElement('strong'); title.textContent = label; title.style.marginRight = 'auto';
    const status = document.createElement('span'); status.setAttribute('role', 'status'); status.textContent = 'Loading editor…';
    const apply = makeButton('Return to Studio', () => { status.textContent = 'Exporting model…'; send('export'); });
    apply.disabled = true; apply.id = 'axioms-editor-return';
    const back = makeButton('Back without applying', () => { dialog.close(); document.querySelector('canvas')?.focus(); });
    toolbar.append(title, status, apply, back);
    const frame = document.createElement('iframe');
    frame.title = label; frame.id = 'axioms-model-editor'; frame.src = url.href;
    frame.setAttribute('allow', 'clipboard-write');
    frame.style.cssText = 'width:100%;height:calc(100% - 52px);border:0;display:block';
    dialog.append(toolbar, frame); document.body.append(dialog);
    editor = { context, token: crypto.randomUUID(), source, filename: safeName(filename), callback, dialog,
      frame, status, apply, ready: false, timer: null };
    editor.timer = setTimeout(() => {
      if (editor?.dialog === dialog && !editor.ready) status.textContent = 'Editor did not load. Close and retry, or use file export/import.';
    }, 45000);
    dialog.addEventListener('cancel', () => { /* Escape hides, preserving the editor draft. */ });
    dialog.showModal();
  }
  function acceptReturn(context, accepted, message) {
    if (!editor || context !== editor.context) return;
    editor.status.textContent = message;
    if (accepted) { editor.dialog.close(); document.querySelector('canvas')?.focus(); }
    else editor.apply.disabled = false;
  }
  window.addEventListener('message', event => {
    const current = editor, data = event.data;
    if (!current || event.origin !== location.origin || event.source !== current.frame.contentWindow ||
        !data || data.protocol !== PROTOCOL) return;
    if (data.type === 'ready' && !current.ready) {
      current.ready = true; clearTimeout(current.timer); current.apply.disabled = false;
      current.status.textContent = 'Edit the model, then return to preview.';
      current.frame.contentWindow.postMessage({ protocol: PROTOCOL, type: 'open', token: current.token,
        context: current.context, filename: current.filename, source: current.source }, location.origin);
      return;
    }
    if (data.token !== current.token || data.context !== current.context) return;
    if (data.type === 'error') {
      current.status.textContent = String(data.message).slice(0, 300);
      current.callback(current.context, 'error', current.status.textContent, null, '');
    } else if (data.type === 'result') {
      if (!(data.glb instanceof ArrayBuffer) || data.glb.byteLength < 20 || data.glb.byteLength > MAX ||
          typeof data.source !== 'string' || new TextEncoder().encode(data.source).length > MAX) {
        current.status.textContent = 'Returned model exceeds the integration limits.'; return;
      }
      current.source = data.source;
      current.callback(current.context, 'ok', current.filename, data.glb, data.source);
    }
  });
  window.AxiomsAuthoring = Object.freeze({ pick, cancelPick, openEditor, closeEditor, acceptReturn, report,
    get state() { return Object.freeze({ ...state }); }, protocol: PROTOCOL });
})();
