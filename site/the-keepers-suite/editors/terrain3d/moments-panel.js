'use strict';
// Optional native-source gallery. The complete editor retains every editing tool.
(() => {
  const scope = new URL('.', location.href).pathname;
  const store = AxiomsNativeMoments({scope});
  const urls = [], selected = new Set();
  let cards = [], loading = false, revision = 0;
  const element = (tag, text, parent, className) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    parent?.append(node); return node;
  };
  const button = (text, parent, action, className) => {
    const node = element('button', text, parent, className); node.type = 'button';
    node.addEventListener('click', action); return node;
  };
  const launcher = button('Experiment shelf', document.querySelector('header'), () => {
    dialog.showModal(); label.focus(); refresh();
  });
  launcher.id = 'moments-open';
  const dialog = element('dialog', '', document.body); dialog.id = 'moments-dialog';
  dialog.setAttribute('aria-labelledby', 'moments-title');
  const top = element('div', '', dialog, 'moments-top');
  const heading = element('div', '', top);
  element('h2', 'Keep your discoveries', heading).id = 'moments-title';
  element('p', 'Try a bold change. Keep the idea. Explore another.', heading);
  button('Close', top, () => dialog.close()).setAttribute('aria-label', 'Close experiment shelf');
  const form = element('form', '', dialog); form.id = 'moments-form';
  const field = element('label', 'Name this moment', form);
  const label = element('input', '', field); label.id = 'moment-name';
  label.maxLength = 64; label.placeholder = 'Needle ridge, wide saddle…'; label.autocomplete = 'off'; label.required = true;
  const keep = element('button', 'Keep current idea', form, 'moments-primary'); keep.type = 'submit';
  element('p', 'Complete native project snapshots—not just pictures. Stored only in this browser; native downloads are your independent backups.', dialog);
  const budget = element('p', '', dialog); budget.className = 'moment-facts';
  const status = element('p', '', dialog); status.id = 'moments-status'; status.setAttribute('role', 'status');
  const grid = element('section', '', dialog); grid.id = 'moments-cards'; grid.setAttribute('aria-label', 'Saved experiments');
  const comparison = element('section', '', dialog); comparison.id = 'moments-compare'; comparison.hidden = true;
  function say(text) { status.textContent = text; }
  function releaseImages() { while (urls.length) URL.revokeObjectURL(urls.pop()); }
  function preview(card, parent) {
    if (!card.preview) return element('div', 'No saved preview', parent, 'moment-preview moment-placeholder');
    const image = element('img', '', parent, 'moment-preview'); image.alt = 'Saved view of ' + card.name;
    const url = URL.createObjectURL(new Blob([card.preview], {type: 'image/png'})); urls.push(url); image.src = url;
    return image;
  }
  async function download(card) {
    try {
      const saved = await store.read(card.id);
      const url = URL.createObjectURL(new Blob([saved.bytes], {type: 'application/zip'}));
      const link = element('a'); link.href = url;
      link.download = (card.name.replace(/[^a-zA-Z0-9_-]/g, '-').slice(0, 64) || 'experiment') + '.zip';
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 30000);
      say('Downloaded the complete native project: ' + card.name);
    } catch (error) { say(error.message); }
  }
  function render() {
    const focused = document.activeElement?.dataset.momentControl;
    releaseImages(); grid.replaceChildren(); comparison.replaceChildren();
    const busy = loading || !!window.AxiomsFullEditor?.getState().exporting;
    keep.disabled = busy || !window.AxiomsFullEditor?.getState().ready;
    budget.textContent = `${cards.length} / ${store.limits.maxItems} moments · ${Math.round(store.limits.maxBytes / 1048576)} MiB shelf budget. Nothing is automatically deleted.`;
    if (!cards.length) element('p', 'Your next experiment belongs here. Name the current idea and keep it before trying something different.', grid);
    for (const card of cards) {
      const tile = element('article', '', grid, 'moment-card'); tile.dataset.momentId = card.id;
      preview(card, tile); element('h3', card.name, tile);
      element('p', `${(card.bytes / 1048576).toFixed(1)} MiB · ${card.format}\n${new Date(card.createdAt).toLocaleString()}`, tile, 'moment-facts');
      const choose = element('label', '', tile, 'moment-select');
      const checkbox = element('input', '', choose); checkbox.type = 'checkbox'; checkbox.dataset.momentControl = 'compare-' + card.id; checkbox.checked = selected.has(card.id);
      element('span', 'Compare this view', choose);
      checkbox.addEventListener('change', () => {
        if (checkbox.checked && selected.size >= 2) { checkbox.checked = false; say('Choose two moments for visual comparison.'); return; }
        checkbox.checked ? selected.add(card.id) : selected.delete(card.id); render();
      });
      const actions = element('div', '', tile, 'moment-actions');
      const reopen = button('Reopen safely', actions, () => {
        if (!confirm(`Reopen “${card.name}”? Its native tool scripts can execute. Current edits will first be kept as a recovery moment. If that cannot be saved, nothing will be opened.`)) return;
        try {
          if (!AxiomsFullEditor.reopenMoment(card.id)) throw new Error('The editor is not ready or is already saving.');
          say('Keeping current edits before reopening…'); render();
        } catch (error) { say(error.message); }
      }, 'moments-primary');
      reopen.dataset.momentControl = 'reopen-' + card.id;
      reopen.disabled = busy || !window.AxiomsFullEditor?.getState().ready;
      button('Download', actions, () => download(card)).disabled = busy;
      button('Remove', actions, async () => {
        if (!confirm(`Remove the saved moment “${card.name}”? Keep a native download first. The open editor project will not be changed.`)) return;
        try { await store.remove(card.id); selected.delete(card.id); await refresh(); say('Removed saved moment: ' + card.name); }
        catch (error) { say(error.message); }
      }).disabled = busy;
    }
    const chosen = cards.filter(card => selected.has(card.id)); comparison.hidden = chosen.length !== 2;
    if (chosen.length === 2) {
      element('h3', 'Two directions. Your choice.', comparison);
      element('p', 'Visual comparison only. These saved views may use different cameras or lighting; this is not a structural or gameplay analysis.', comparison);
      const pair = element('div', '', comparison, 'moment-pair');
      for (const card of chosen) { const figure = element('figure', '', pair); preview(card, figure); element('figcaption', card.name, figure); }
    }
    if (focused) dialog.querySelector('[data-moment-control="' + CSS.escape(focused) + '"]')?.focus({preventScroll:true});
  }
  async function refresh() {
    const ticket = ++revision; loading = true;
    try { const found = await store.list(); if (ticket !== revision) return; cards = found; for (const key of selected) if (!cards.some(card => card.id === key)) selected.delete(key); }
    catch (error) { say('Shelf unavailable: ' + error.message + ' The native editor and downloads remain available.'); }
    finally { if (ticket === revision) { loading = false; if (dialog.open) render(); } }
  }
  form.addEventListener('submit', event => {
    event.preventDefault();
    try {
      const name = store.validateName(label.value);
      if (!AxiomsFullEditor.keepMoment(name)) throw new Error('The editor is not ready or is already saving.');
      say('Saving the current native project…'); render();
    } catch (error) { say(error.message); }
  });
  window.addEventListener('axioms-moment-state', () => { if(dialog.open) render(); });
  window.addEventListener('axioms-moment-result', async event => {
    await refresh(); say(String(event.detail?.message || 'Experiment updated.'));
  });
  dialog.addEventListener('close', () => { ++revision; loading = false; releaseImages(); launcher.focus(); });
})();
