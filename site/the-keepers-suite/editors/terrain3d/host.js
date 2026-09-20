'use strict';
// Lifecycle and native-project transport only; Godot + Terrain3D own editing.
(() => {
  const MAX_BYTES = 512 * 1024 * 1024, MAX_FILES = 12000;
  const status = document.getElementById('status'), button = document.getElementById('download');
  const returnButton = document.getElementById('return'), canvas = document.getElementById('editor');
  const pending = [], diagnostics = [];
  let ready = false, fatal = '', lastState = {}, manifest, exporting = '', inspection = 0, lastReceipt = null;
  const params = new URLSearchParams(location.hash.slice(1));
  const session = params.get('session') || '', context = params.get('context') || '';
  const parentOrigin = location.origin;
  const hostRoot = new URL('.', location.href);
  const momentStore = AxiomsNativeMoments({scope: hostRoot.pathname});
  const captureGuard = AxiomsCaptureGuard(canvas);
  let momentAction = null;
  function momentResult(message) { window.dispatchEvent(new CustomEvent('axioms-moment-result', {detail:{message}})); }
  let returnURL = null;
  if (params.has('return')) {
    const candidate = new URL(params.get('return'), location.href);
    if (candidate.origin === location.origin && !candidate.username && !candidate.password && hostRoot.pathname.startsWith(candidate.pathname) && candidate.pathname.endsWith('/')) returnURL = candidate;
  }
  if (returnButton) returnButton.hidden = !returnURL;
  function message(error, terminal = false) {
    const text = String(error?.message || error);
    if (terminal) fatal = text;
    status.textContent = text;
    const box = document.getElementById('error');
    box.textContent = text; box.style.display = 'block';
    button.disabled = !ready;
    if (returnButton) returnButton.disabled = !ready;
    exporting = ''; momentAction = null;
    captureGuard.end();
    document.getElementById('open').disabled = !ready;
    document.getElementById('new').disabled = !ready;
    momentResult(text);
    if (terminal) console.error('FULL_EDITOR_HOST:', text);
  }
  function clearMessage() { document.getElementById('error').style.display = 'none'; }
  function emit(type, data) {
    if (parent !== window && session && context) parent.postMessage({protocol:'axioms.full-editor/1',type,session,context,...data}, parentOrigin);
  }
  const sha = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
  function pathOK(path) {
    return typeof path === 'string' && path.length <= 1024 && !path.startsWith('/') && !/[\\\u0000-\u001f:]/.test(path) && !path.split('/').some(p=>!p || p==='.' || p==='..');
  }
  async function getFile(item) {
    if (!pathOK(item.path) || !Number.isSafeInteger(item.bytes) || item.bytes<0 || !/^[0-9a-f]{64}$/.test(item.sha256)) throw new Error('Invalid project manifest entry');
    const url = new URL(item.url,location.href);
    if (url.origin!==location.origin || !url.pathname.startsWith(new URL('project/',location.href).pathname)) throw new Error('Project dependency escapes its owned folder');
    const response=await fetch(url);
    if (!response.ok) throw new Error(`Cannot load ${item.path}: HTTP ${response.status}`);
    const bytes=await response.arrayBuffer();
    if (bytes.byteLength!==item.bytes || await sha(bytes)!==item.sha256) throw new Error(`Project identity mismatch: ${item.path}`);
    return bytes;
  }
  function download(bytes,name) {
    const url=URL.createObjectURL(new Blob([bytes],{type:'application/zip'}));
    const link=document.createElement('a');link.href=url;link.download=name;link.click();
    setTimeout(()=>URL.revokeObjectURL(url),30000);
  }
  function requestExport(mode) {
    if (!ready || exporting) return false;
    if (!captureGuard.begin('Capturing the current native scene and its preview…')) return false;
    document.getElementById('open').disabled = true;
    document.getElementById('new').disabled = true;
    clearMessage(); exporting=mode;button.disabled=true;
    if (returnButton) returnButton.disabled=true;
    status.textContent='Saving native scene, textures, terrain regions and instances…';
    pending.push('export-project');
    return true;
  }
  window.AxiomsFullEditor=Object.freeze({
    keepMoment(name){
      if (!ready || exporting) return false;
      momentAction={kind:'keep',name:momentStore.validateName(name)};
      return requestExport('moment');
    },
    reopenMoment(id){
      if (!ready || exporting) return false;
      if (typeof id!=='string' || !/^[a-f0-9-]{36}$/.test(id)) throw new Error('Invalid moment identity.');
      momentAction={kind:'reopen',id};
      return requestExport('moment');
    },
    takeRequest(){return pending.shift() || '';},
    inspect(full=true){const kind=full?'inspect':'inspect-controls';if(ready && !pending.includes(kind))pending.push(kind);return inspection;},
    report(json){
      const wasReady=ready;
      const report=JSON.parse(json);lastState=report;ready=report.ready===true;inspection++;
      if(wasReady!==ready)window.dispatchEvent(new Event('axioms-moment-state'));
      button.disabled=!ready || !!exporting;
      document.getElementById('open').disabled=!ready || !!exporting;
      document.getElementById('new').disabled=!ready || !!exporting;
      if (returnButton) returnButton.disabled=!ready || !!exporting;
      if (report.error){message(report.error);return;}
      if (ready){
        if (!exporting) status.textContent='Full Terrain3D editor · save the native project to retain every authored feature';
        document.body.dataset.editorReady='true';emit('ready',{state:report});
      }
    },
    async deliverProject(base64,metadata){
      const mode=exporting || 'download', action=momentAction;
      captureGuard.update('Verifying the complete native project…');
      try{
        if (typeof base64!=='string' || base64.length>MAX_BYTES*4/3+4) throw new Error('Returned project exceeds the transfer budget');
        const bytes=Uint8Array.from(atob(base64),c=>c.charCodeAt(0)),receipt=JSON.parse(metadata);
        if (receipt.format!=='godot-native-project' || await sha(bytes)!==receipt.sha256) throw new Error('Returned native project failed byte verification');
        const files=await AxiomsProjectIO.decode(bytes,manifest);
        if (mode==='download') download(bytes,'terrain-project.zip');
        captureGuard.update('Keeping a verified source copy…');
        try{await AxiomsProjectIO.stage(bytes,receipt,files['studio-preview.png'] || null);}
        catch(error){
          if(mode!=='download') download(bytes,'terrain-project.zip');
          throw new Error('The complete project was downloaded, but browser storage failed. Keep the ZIP; the previous stored project is unchanged.');
        }
        let experiment=null;
        if(mode==='moment'){
          captureGuard.update(action?.kind==='reopen' ? 'Keeping current edits before reopening your idea…' : 'Adding this idea to your experiment shelf…');
          try{
            experiment=await AxiomsNativeMomentJourney(action,
              {bytes,format:receipt.format,receipt,preview:files['studio-preview.png'] || null},
              {store:momentStore,admit:value=>AxiomsProjectIO.decode(value,manifest),
               open:value=>AxiomsProjectIO.stage(value.bytes,value.receipt,value.preview)});
          }catch(error){
            download(bytes,'terrain-project.zip');
            throw new Error(String(error.message || error)+' Current edits remain open and their complete native project was downloaded.');
          }
        }
        momentAction=null;
        lastReceipt=receipt;emit('project-saved',{receipt,bytes:bytes.buffer});
        exporting='';button.disabled=false;if(returnButton)returnButton.disabled=false;
        document.getElementById('open').disabled=false;document.getElementById('new').disabled=false;
        if(experiment){momentResult(experiment.message);if(experiment.reload){location.reload();return;}}
        status.textContent='Complete native project saved. Textures, control maps, mesh assets and placements are retained.';
        if(mode==='return' && returnURL){returnURL.searchParams.set('editor_saved',receipt.sha256.slice(0,12));location.assign(returnURL.href);return;}
        captureGuard.end();
      }catch(error){message(error);}
    },
    getState(){return structuredClone({ready,fatal,state:lastState,diagnostics,inspection,receipt:lastReceipt,exporting,input_locked:captureGuard.active});},
  });
  button.addEventListener('click',()=>requestExport('download'));
  if(returnButton)returnButton.addEventListener('click',()=>requestExport('return'));
  const input=document.getElementById('project-file');
  document.getElementById('open').addEventListener('click',()=>{input.value='';input.click();});
  input.addEventListener('change',async()=>{
    const file=input.files?.[0];if(!file || !manifest)return;
    try{
      if(file.size>MAX_BYTES)throw new Error('Project exceeds the browser transfer budget');
      const bytes=new Uint8Array(await file.arrayBuffer());
      const files=await AxiomsProjectIO.decode(bytes,manifest);
      if(!confirm('Open this trusted native project? Godot tool scripts can execute. Save the current project first; unsaved edits will be replaced.'))return;
      await AxiomsProjectIO.stage(bytes,null,files['studio-preview.png'] || null);location.reload();
    }catch(error){message(error);}
  });
  document.getElementById('new').addEventListener('click',async()=>{
    if(!confirm('Start a new project? Save the current project first to retain its edits.'))return;
    try{await AxiomsProjectIO.clear();location.reload();}catch(error){message(error);}
  });
  window.addEventListener('message',event=>{
    const value=event.data;
    if(event.origin!==parentOrigin || event.source!==parent || !session || !context || value?.protocol!=='axioms.full-editor/1' || value.session!==session || value.context!==context)return;
    if(value.type==='export-project')requestExport('download');
  });
  function diagnostic(line,error){
    const text=String(line);diagnostics.push({error,text:text.slice(0,1000)});
    if(diagnostics.length>80)diagnostics.shift();(error?console.warn:console.log)(text);
  }
  async function start(){
    await AxiomsEditorIsolation();
    const response=await fetch('project-manifest.json');
    if(!response.ok)throw new Error('Full editor project manifest is unavailable');
    manifest=await response.json();
    if(manifest.schema!==1 || !Array.isArray(manifest.files) || manifest.files.length>MAX_FILES || !Array.isArray(manifest.gdextension_libs))throw new Error('Unsupported full-editor package');
    if(new Set(manifest.files.map(f=>f.path)).size!==manifest.files.length || manifest.files.reduce((n,f)=>n+f.bytes,0)>MAX_BYTES)throw new Error('Invalid project dependency inventory');
    const stored=await AxiomsProjectIO.read();
    const restored=stored?await AxiomsProjectIO.decode(stored,manifest):null;
    const pools={emscriptenPoolSize:48,godotPoolSize:4};diagnostic('FULL_EDITOR_POOLS '+JSON.stringify(pools),false);
    const engine=new Engine({executable:'godot.editor',canvas,locale:'en',canvasResizePolicy:0,...pools,
      gdextensionLibs:manifest.gdextension_libs,persistentPaths:['/home/web_user'],
      onPrint:line=>diagnostic(line,false),onPrintError:line=>diagnostic(line,true),
      onExit:code=>{ready=false;message(`Editor closed (${code}). Reopen the saved native project to continue.`);}});
    await engine.init('godot.editor');
    let entry='res://world.tscn';
    if(restored){
      for(const[name,bytes]of Object.entries(restored))await engine.preloadFile(bytes,'/project/'+name);
      if(restored['studio-project.json']){
        const saved=JSON.parse(new TextDecoder().decode(restored['studio-project.json']));
        if(typeof saved.entry_scene!=='string' || !saved.entry_scene.startsWith('res://') || !pathOK(saved.entry_scene.slice(6)) || !restored[saved.entry_scene.slice(6)])throw new Error('Saved project entry is invalid');
        entry=saved.entry_scene;
      }
    }else{
      let next=0,loaded=0;
      await Promise.all(Array.from({length:6},async()=>{
        while(next<manifest.files.length){const item=manifest.files[next++];await engine.preloadFile(await getFile(item),'/project/'+item.path);status.textContent=`Loading native project: ${++loaded}/${manifest.files.length}`;}
      }));
    }
    await engine.preloadFile(new TextEncoder().encode('res://addons/terrain_3d/terrain.gdextension\n'),'/project/.godot/extension_list.cfg');
    function resize(){const box=canvas.getBoundingClientRect();const w=Math.max(1,Math.round(box.width*devicePixelRatio)),h=Math.max(1,Math.round(box.height*devicePixelRatio));if(canvas.width!==w)canvas.width=w;if(canvas.height!==h)canvas.height=h;}
    new ResizeObserver(resize).observe(canvas);resize();status.textContent='Opening the complete Godot editor and Terrain3D plugin…';
    const args=['--editor','--single-window','--path','/project',entry];
    if(params.get('debug')==='1')args.unshift('--verbose');
    await engine.start({args});
  }
  start().catch(error=>message(error,true));
})();
