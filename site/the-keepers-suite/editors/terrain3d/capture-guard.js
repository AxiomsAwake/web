'use strict';
// Freeze authoring input, not the native engine loop, while a source copy is made.
window.AxiomsCaptureGuard = function (canvas) {
  if (!(canvas instanceof HTMLCanvasElement)) throw new Error('Capture needs an editor canvas.');
  const dialog = document.createElement('dialog');
  dialog.id = 'native-capture-dialog';
  dialog.setAttribute('aria-labelledby', 'native-capture-title');
  dialog.setAttribute('aria-describedby', 'native-capture-detail');
  const title = document.createElement('h2');
  title.id = 'native-capture-title'; title.textContent = 'Keeping your work safe';
  const progress = document.createElement('p');
  progress.id = 'native-capture-progress'; progress.setAttribute('role', 'status');
  const detail = document.createElement('p');
  detail.id = 'native-capture-detail';
  detail.textContent = 'Editing is paused while the complete native project is captured. Keep this tab open; failed saves leave your draft here.';
  dialog.append(title, progress, detail);
  const style = document.createElement('style');
  style.textContent = `
    #native-capture-dialog{box-sizing:border-box;width:min(460px,calc(100vw - 28px));max-height:calc(100dvh - 28px);overflow:auto;padding:24px;border:1px solid #7aa897;border-radius:16px;background:#101f28;color:#e6f0f3;font:15px/1.5 system-ui,sans-serif}
    #native-capture-dialog::backdrop{background:rgba(4,10,16,.68)}
    #native-capture-dialog h2{margin:0 0 12px;font-size:24px;line-height:1.2}
    #native-capture-progress{padding:12px 0;border-block:1px solid #355466;font-weight:600;color:#b9eddb}
    #native-capture-detail{margin:12px 0 0;color:#bbcdd5}
  `;
  document.head.append(style); document.body.append(dialog);
  let active = false, previousFocus = null, previousInert = false, previousBusy = null;
  // Capture listeners precede the native engine's input listeners. A modal alone
  // does not stop a canvas engine listening to keyboard input on the document.
  const events = ['keydown', 'keypress', 'keyup', 'beforeinput', 'input',
    'pointerdown', 'pointerup', 'pointermove', 'pointercancel',
    'mousedown', 'mouseup', 'mousemove', 'click', 'dblclick',
    'touchstart', 'touchend', 'touchmove', 'contextmenu', 'wheel'];
  const shield = event => {
    if (!active) return;
    // Programmatic native downloads are deliberately delivered during capture.
    if (event.type === 'click' && !event.isTrusted && event.target instanceof HTMLAnchorElement &&
        event.target.hasAttribute('download') && event.target.href.startsWith('blob:')) return;
    event.stopImmediatePropagation();
    if (!(event.type === 'keydown' && event.key === 'Tab') &&
        !(event.type === 'wheel' && dialog.contains(event.target))) event.preventDefault();
  };
  for (const type of events) window.addEventListener(type, shield, {capture:true, passive:false});
  dialog.addEventListener('cancel', event => event.preventDefault());
  function end() {
    if (!active) return;
    active = false;
    dialog.close();
    canvas.inert = previousInert;
    if (previousBusy === null) canvas.removeAttribute('aria-busy');
    else canvas.setAttribute('aria-busy', previousBusy);
    if (previousFocus?.isConnected && !previousFocus.closest('[inert]')) previousFocus.focus({preventScroll:true});
    else if (!canvas.inert) canvas.focus({preventScroll:true});
  }
  return Object.freeze({
    begin(text) {
      if (active) return false;
      previousFocus = document.activeElement; previousInert = canvas.inert;
      previousBusy = canvas.getAttribute('aria-busy');
      active = true; canvas.blur(); canvas.inert = true; canvas.setAttribute('aria-busy', 'true');
      progress.textContent = String(text);
      try { dialog.showModal(); } catch (error) { end(); throw error; }
      return true;
    },
    update(text) { if (active) progress.textContent = String(text); },
    end,
    get active() { return active; },
    destroy() {
      end();
      for (const type of events) window.removeEventListener(type, shield, true);
      dialog.remove(); style.remove();
    },
  });
};
