(()=>{'use strict';
const feedback=globalThis.AxiomsPlayerFeedback;
if(!feedback)return;
const badge=document.getElementById('ll-build-id');
const compact=text=>String(text||'').replace(/\s+/g,' ').trim();
const integer=value=>value===null||value===undefined||value===''?null:(Number.isFinite(Number(value))?Math.round(Number(value)):null);
const token=(value,fallback='unknown',limit=32)=>{
  const text=compact(value).replace(/[^a-z0-9_.:/-]/gi,'?').slice(0,limit);
  return text||fallback;
};
function collectLoadState(){
  const ll=globalThis.LittleLines?.v2?.ll;
  if(!ll)return {};
  let report=null;
  try{report=ll.loadOperation?.snapshot?.()||null;}catch{}
  if(!report)return {};
  const rows=Array.isArray(report.rows)?report.rows:[];
  const completed=integer(report.completed),total=integer(report.total),elapsed=integer(report.elapsedMs);
  const buildMs=integer(ll.metrics?.buildMs),identityMs=integer(ll.metrics?.identityMs),networkCalls=integer(ll.broker?.count);
  const loadStages=rows.slice(0,12).map(row=>{
    const ms=integer(row?.elapsedMs);
    return `${token(row?.id,'stage',24)}:${token(row?.state,'unknown',16)}:${ms??0}ms`;
  });
  return {
    loadStatus:token(report.status,'unknown',24),
    loadElapsedMs:elapsed??'unknown',
    loadProgress:`${completed??0}/${total??rows.length}`,
    loadStages:loadStages.length?loadStages:['none'],
    cacheMode:token(ll.cache?.mode,'unknown',32),
    networkCalls:networkCalls??'unknown',
    sceneReused:ll.metrics?.sceneReused===true?'yes':ll.metrics?.sceneReused===false?'no':'unknown',
    mapBuildMs:buildMs??'unknown',
    landscapeIdentityMs:identityMs??'unknown'
  };
}
function collectState(){
  const openPanels=[...document.querySelectorAll('.panel.open')].map(panel=>panel.id||'panel');
  const status=document.querySelector('.statuscard');
  const fatal=document.getElementById('fatal');
  const visibleFatal=fatal&&getComputedStyle(fatal).display!=='none';
  return {
    buildLabel:compact(badge?.textContent)||'unknown',
    sourceRevision:badge?.dataset?.sourceRevision||'unknown',
    openPanels,
    cleanView:document.body.classList.contains('clean')?'on':'off',
    rendererQuality:compact(document.getElementById('quality')?.textContent)||'unknown',
    status:compact(status?.textContent)||'—',
    routeItems:document.querySelectorAll('.routeitem').length,
    fatalError:visibleFatal?compact(fatal.textContent):'none',
    ...collectLoadState()
  };
}
feedback.installFeedbackButton({
  game:'Little Lines',site:'little-lines',issueUrl:'https://github.com/AxiomsAwake/web/issues/new',
  host:document.body,id:'playerFeedbackBtn',buildInfoUrl:false,
  build:compact(badge?.textContent)||undefined,getState:collectState
});
})();
