(()=>{'use strict';
const feedback=globalThis.AxiomsPlayerFeedback;
if(!feedback)return;
const CRITICAL_FILES=new Set(['index.js','index.wasm','index.pck']);
const FAILURE_STATUS=/\b(error|fail(?:ed|ure)?|unable|unsupported|abort(?:ed)?|exception)\b/i;
let buildPromise;
let bootstrapFailure=false;
function loadBuild(){
  if(!buildPromise)buildPromise=fetch('./build.json',{cache:'no-store',credentials:'same-origin'}).then(r=>r.ok?r.json():null).catch(()=>null);
  return buildPromise;
}
function finiteNumber(value){const n=Number(value);return Number.isFinite(n)&&n>=0?n:null;}
function roundedMs(value){const n=finiteNumber(value);return n===null?null:Number(n.toFixed(1));}
function resourceFileName(value){
  try{
    const pathname=new URL(String(value||''),globalThis.location?.href||'https://invalid.local/').pathname;
    const file=pathname.split('/').filter(Boolean).pop()||'';
    return CRITICAL_FILES.has(file)?file:'';
  }catch(_){return '';}
}
function collectStartupTiming(env=globalThis){
  try{
    const perf=env.performance;
    if(!perf?.getEntriesByType)return {available:false,navigation:{},resources:{}};
    const nav=perf.getEntriesByType('navigation')?.[0];
    const navigation=nav?{
      type:['navigate','reload','back_forward','prerender'].includes(String(nav.type))?String(nav.type):'unknown',
      response_start_ms:roundedMs(nav.responseStart),
      response_end_ms:roundedMs(nav.responseEnd),
      dom_interactive_ms:roundedMs(nav.domInteractive),
      dom_content_loaded_ms:roundedMs(nav.domContentLoadedEventEnd),
      load_event_end_ms:roundedMs(nav.loadEventEnd)
    }:{};
    const resources={};
    for(const entry of perf.getEntriesByType('resource')||[]){
      const file=resourceFileName(entry?.name);
      if(!file)continue;
      resources[file]={
        start_ms:roundedMs(entry.startTime),
        duration_ms:roundedMs(entry.duration),
        transfer_bytes:finiteNumber(entry.transferSize),
        encoded_bytes:finiteNumber(entry.encodedBodySize),
        decoded_bytes:finiteNumber(entry.decodedBodySize)
      };
    }
    return {available:Boolean(nav)||Object.keys(resources).length>0,navigation,resources};
  }catch(_){return {available:false,navigation:{},resources:{}};}
}
function publishHostDiagnostics(){
  try{
    const value=feedback.collectEnvironment(globalThis);
    value.Startup=collectStartupTiming(globalThis);
    globalThis.__KEEPERS_HOST_DIAGNOSTICS_JSON__=JSON.stringify(value);
  }catch(_){globalThis.__KEEPERS_HOST_DIAGNOSTICS_JSON__='';}
}
globalThis.__KEEPERS_COLLECT_STARTUP_TIMING__=collectStartupTiming;
publishHostDiagnostics();
globalThis.addEventListener?.('resize',publishHostDiagnostics,{passive:true});
globalThis.addEventListener?.('load',publishHostDiagnostics,{once:true});
const style=document.createElement('style');
style.textContent='#playerFeedbackBtn{position:fixed;right:max(10px,env(safe-area-inset-right));top:max(10px,env(safe-area-inset-top));z-index:100000;min-height:38px;padding:8px 11px;border:1px solid rgba(255,255,255,.28);border-radius:9px;background:rgba(10,18,28,.84);color:#f4f7fb;box-shadow:0 4px 18px rgba(0,0,0,.3);font:600 12px/1.1 system-ui,sans-serif;cursor:pointer;backdrop-filter:blur(5px)}#playerFeedbackBtn[hidden]{display:none}#playerFeedbackBtn:hover,#playerFeedbackBtn:focus-visible{background:rgba(25,40,58,.96);outline:2px solid rgba(255,255,255,.55);outline-offset:2px}@media(max-width:640px){#playerFeedbackBtn{top:auto;bottom:max(10px,env(safe-area-inset-bottom));font-size:11px;padding:8px 10px}}';
document.head.appendChild(style);
async function state(){
  publishHostDiagnostics();
  const build=await loadBuild();
  const canvas=document.querySelector('canvas');
  const rect=canvas?.getBoundingClientRect();
  const status=[...document.querySelectorAll('[role="status"],#status-notice,#status')].map(x=>x.textContent?.replace(/\s+/g,' ').trim()).filter(Boolean).slice(0,3);
  return {
    version:build?.version||'unknown',
    sourceRevision:build?.source_revision||'unknown',
    target:build?.target||'web',
    documentState:document.visibilityState,
    windowFocused:document.hasFocus()?'yes':'no',
    fullscreen:document.fullscreenElement?'yes':'no',
    canvas:canvas?`${canvas.width}×${canvas.height} internal · ${Math.round(rect?.width||0)}×${Math.round(rect?.height||0)} CSS`:'not found',
    canvasFocused:canvas&&document.activeElement===canvas?'yes':'no',
    status:status.length?status:'none'
  };
}
const hostFeedbackButton=feedback.installFeedbackButton({
  game:'The Keepers',site:'the-keepers',host:document.body,id:'playerFeedbackBtn',buildInfoUrl:false,
  getBuild:async()=>{const build=await loadBuild();return build?{version:`${build.version||'unknown'} · ${build.source_revision||'unknown'}`} : null;},
  getState:state
});
function statusShowsFailure(){
  return [...document.querySelectorAll('[role="status"],#status-notice,#status')]
    .some(node=>FAILURE_STATUS.test(node.textContent||''));
}
function syncHostFeedback(){
  const nativeFeedbackAvailable=document.querySelector('canvas')?.dataset?.keepersReady==='true';
  hostFeedbackButton.hidden=nativeFeedbackAvailable&&!bootstrapFailure&&!statusShowsFailure();
}
function exposeHostFeedback(){bootstrapFailure=true;syncHostFeedback();}
globalThis.addEventListener?.('error',exposeHostFeedback);
globalThis.addEventListener?.('unhandledrejection',exposeHostFeedback);
globalThis.addEventListener?.('keepers-native-feedback-ready',syncHostFeedback);
document.querySelector('canvas')?.addEventListener?.('webglcontextcreationerror',exposeHostFeedback);
if(globalThis.MutationObserver){
  new globalThis.MutationObserver(syncHostFeedback).observe(document.body,{childList:true,subtree:true,characterData:true});
}
syncHostFeedback();
})();
