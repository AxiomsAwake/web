(()=>{'use strict';
const feedback=globalThis.AxiomsPlayerFeedback;
if(!feedback)return;
let buildPromise;
function loadBuild(){
  if(!buildPromise)buildPromise=fetch('./build.json',{cache:'no-store',credentials:'same-origin'}).then(r=>r.ok?r.json():null).catch(()=>null);
  return buildPromise;
}
const style=document.createElement('style');
style.textContent='#playerFeedbackBtn{position:fixed;right:max(10px,env(safe-area-inset-right));top:max(10px,env(safe-area-inset-top));z-index:100000;min-height:38px;padding:8px 11px;border:1px solid rgba(255,255,255,.28);border-radius:9px;background:rgba(10,18,28,.84);color:#f4f7fb;box-shadow:0 4px 18px rgba(0,0,0,.3);font:600 12px/1.1 system-ui,sans-serif;cursor:pointer;backdrop-filter:blur(5px)}#playerFeedbackBtn:hover,#playerFeedbackBtn:focus-visible{background:rgba(25,40,58,.96);outline:2px solid rgba(255,255,255,.55);outline-offset:2px}@media(max-width:640px){#playerFeedbackBtn{top:auto;bottom:max(10px,env(safe-area-inset-bottom));font-size:11px;padding:8px 10px}}';
document.head.appendChild(style);
async function state(){
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
feedback.installFeedbackButton({
  game:'The Keepers',site:'the-keepers',host:document.body,id:'playerFeedbackBtn',buildInfoUrl:false,
  getBuild:async()=>{const build=await loadBuild();return build?{version:`${build.version||'unknown'} · ${build.source_revision||'unknown'}`} : null;},
  getState:state
});
})();
