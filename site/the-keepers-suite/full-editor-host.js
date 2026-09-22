'use strict';
(() => {
  const ENTRY = "editors/terrain3d/";
  const TOP_LEVEL_EDITOR = new URL(ENTRY, document.baseURI).href;
  const provider = AxiomsGodotProjectProvider({entry:ENTRY, workspace:'terrain'});
  AxiomsNativeProjects.register('terrain', provider);
  let active = false, geometry = null, shell = null, frame = null, patchTimer = 0;

  function layout() {
    if (!shell || !geometry) return;
    const canvas = document.querySelector('canvas');
    const box = canvas?.getBoundingClientRect();
    const r = geometry.rect, v = geometry.viewport;
    if (!box || !box.width || !box.height || !Array.isArray(r) || r.length !== 4 ||
        !Array.isArray(v) || v.length !== 2 || v[0] <= 0 || v[1] <= 0) return;
    const sx = box.width / v[0], sy = box.height / v[1];
    const left = Math.max(box.left, box.left + r[0] * sx);
    const top = Math.max(box.top, box.top + r[1] * sy);
    const right = Math.min(box.right, box.left + (r[0] + r[2]) * sx);
    const bottom = Math.min(box.bottom, box.top + (r[1] + r[3]) * sy);
    shell.style.left = String(left) + 'px';
    shell.style.top = String(top) + 'px';
    shell.style.width = String(Math.max(0, right - left)) + 'px';
    shell.style.height = String(Math.max(0, bottom - top)) + 'px';
  }

  function exposeSave() {
    clearTimeout(patchTimer);
    let attempts = 0;
    const patch = () => {
      try {
        const button = frame?.contentDocument?.getElementById('return');
        if (button) {
          button.hidden = false;
          button.textContent = 'Save project';
          button.title = 'Save the complete native project and keep editing here.';
          return;
        }
      } catch { /* Same-origin package may still be navigating. */ }
      if (++attempts < 160) patchTimer = setTimeout(patch, 250);
    };
    patch();
  }

  function ensure() {
    if (shell || !document.body) return;
    shell = document.createElement('section');
    shell.style.cssText = 'position:fixed;z-index:8;overflow:hidden;background:#0d171e;border:0;box-sizing:border-box';
    if (!crossOriginIsolated) {
      shell.id = 'axioms-terrain-fallback';
      shell.setAttribute('aria-label', 'Terrain3D full editor fallback');
      const message = document.createElement('div');
      message.style.cssText = 'display:grid;place-items:center;width:100%;height:100%;padding:24px;box-sizing:border-box;color:#e9edf2;font:16px system-ui,sans-serif;text-align:center';
      const title = document.createElement('h2');
      title.textContent = 'Open the full Terrain3D editor';
      const detail = document.createElement('p');
      detail.textContent = 'Open the complete Terrain3D editor in a separate tab. Download its editable native project to keep or continue your work.';
      const launch = document.createElement('a');
      launch.id = 'axioms-terrain-top-level-editor';
      launch.href = TOP_LEVEL_EDITOR;
      launch.target = '_blank';
      launch.rel = 'noopener';
      launch.textContent = 'Open full Terrain3D editor';
      launch.style.cssText = 'display:inline-block;padding:12px 16px;border-radius:5px;background:#27604c;color:white;text-decoration:none';
      message.append(title, detail, launch);
      shell.append(message);
      document.body.append(shell);
      shell.hidden = !active;
      layout();
      return;
    }
    shell.id = 'axioms-terrain-inline';
    shell.setAttribute('aria-label', 'Terrain3D full editor');
    frame = document.createElement('iframe');
    frame.id = 'axioms-terrain-inline-frame';
    frame.title = 'Terrain3D full editor';
    frame.src = new URL(ENTRY, document.baseURI).href;
    frame.setAttribute('allow', 'clipboard-write');
    frame.style.cssText = 'display:block;width:100%;height:100%;border:0;background:#0d171e';
    frame.addEventListener('load', exposeSave);
    shell.append(frame);
    document.body.append(shell);
    shell.hidden = !active;
    layout();
    setInterval(() => {
      if (active) AxiomsNativeProjects.refresh('terrain');
    }, 1000);
  }

  function setRect(encoded) {
    try {
      const value = JSON.parse(String(encoded));
      if (!Array.isArray(value?.rect) || value.rect.length !== 4 ||
          !Array.isArray(value?.viewport) || value.viewport.length !== 2 ||
          ![...value.rect, ...value.viewport].every(Number.isFinite)) return;
      geometry = value;
      ensure();
      layout();
    } catch { /* Invalid layout reports never affect the editor project. */ }
  }

  function setActive(value) {
    active = value === true;
    ensure();
    if (!shell) return;
    shell.hidden = !active;
    if (active) {
      layout();
      AxiomsNativeProjects.refresh('terrain');
    }
  }

  window.addEventListener('resize', layout);
  window.AxiomsTerrainInline = Object.freeze({setRect, setActive});
})();
