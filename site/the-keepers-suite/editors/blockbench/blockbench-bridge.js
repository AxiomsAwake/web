/* Standalone Blockbench companion; speaks only the artifact protocol to its parent. */
(() => {
  'use strict';
  const protocol = 'axioms-authoring/v1';
  const MAX = 64 * 1024 * 1024;
  let token = '', context = '', busy = false;
  const post = data => parent.postMessage({ protocol, token, context, ...data }, location.origin);
  const ready = () => {
    if (window.Blockbench?.setup_successful && window.Codecs?.project && window.Codecs?.gltf) {
      post({ type: 'ready' }); return true;
    }
    return false;
  };
  const timer = setInterval(() => { if (ready()) clearInterval(timer); }, 100);
  setTimeout(() => clearInterval(timer), 45000);
  window.addEventListener('message', async event => {
    const data = event.data;
    if (event.source !== parent || event.origin !== location.origin || !data || data.protocol !== protocol) return;
    try {
      if (data.type === 'open') {
        if (token || typeof data.source !== 'string' || new TextEncoder().encode(data.source).length > MAX) return;
        if (typeof data.token !== 'string' || typeof data.context !== 'string') return;
        token = data.token; context = data.context;
        const source = JSON.parse(data.source);
        if (!source.meta || !Array.isArray(source.elements)) throw new Error('No valid editable project was supplied.');
        Codecs.project.load(source, { path: String(data.filename || 'unit.bbmodel'), no_file: true });
        window.dispatchEvent(new CustomEvent('axioms-project-opened'));
      } else if (data.type === 'export' && data.token === token && data.context === context && !busy) {
        busy = true;
        if (!window.Project) throw new Error('Open a model before returning to Studio.');
        // Preserve source coordinates; the editor's formatted text serializer can round numbers.
        const source = Codecs.project.compile({ compressed: false, raw: true });
        if (!source || typeof source !== 'object' || Array.isArray(source))
          throw new Error('The editor did not return a raw project. The previous Studio model is unchanged.');
        const text = JSON.stringify(source);
        const glb = await Codecs.gltf.compile({ encoding: 'binary', scale: 16, embed_textures: true, animations: true });
        if (!(glb instanceof ArrayBuffer) || glb.byteLength > MAX || new TextEncoder().encode(text).length > MAX)
          throw new Error('The model exceeds the integration file budget. Save it locally and reduce its size.');
        post({ type: 'result', source: text, glb });
        busy = false;
      }
    } catch (error) { busy = false; post({ type: 'error', message: error.message }); }
  });
})();
