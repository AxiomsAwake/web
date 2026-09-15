/* Shared browser player-feedback composer. No credentials; opens a public issue draft for review. */
(function(root,factory){
  const api=factory(root);
  if(typeof module==='object'&&module.exports) module.exports=api;
  else root.AxiomsPlayerFeedback=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(root){
  'use strict';
  const DEFAULT_ISSUE_URL='https://github.com/AxiomsAwake/web/issues/new';
  const DRAFT_KEY='axioms:last-feedback-draft/v1';
  let lastDraft=null;

  function textValue(value){
    if(value===null||value===undefined||value==='') return '—';
    if(Array.isArray(value)) return value.length?value.join(', '):'none';
    if(typeof value==='object') return JSON.stringify(value);
    return String(value);
  }
  function safeLabel(key){
    return String(key).replace(/[_-]+/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
  }
  function inputDescription(env){
    const nav=env.navigator||{};
    const parts=[];
    if((nav.maxTouchPoints||0)>0) parts.push(`touch (${Math.min(16,Number(nav.maxTouchPoints)||0)})`);
    try{parts.push(env.matchMedia?.('(pointer: coarse)')?.matches?'coarse pointer':'fine pointer');}catch(_){}
    try{if(env.matchMedia?.('(hover: hover)')?.matches) parts.push('hover');}catch(_){}
    return parts.length?parts.join(', '):'unknown';
  }
  function browserDescription(nav){
    const brands=nav?.userAgentData?.brands;
    if(!Array.isArray(brands)) return 'unknown';
    const safe=brands
      .filter(item=>item&&typeof item.brand==='string'&&!/^Not(?:\s|_)?A/i.test(item.brand))
      .slice(0,3)
      .map(item=>`${item.brand.slice(0,32)} ${String(item.version||'').slice(0,16)}`.trim());
    return safe.length?safe.join(', '):'unknown';
  }
  function reducedMotion(env){
    try{return env.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches?'reduce':'no-preference';}catch(_){return 'unknown';}
  }
  function webglDescription(env){
    try{
      const canvas=env.document?.createElement?.('canvas');
      const gl=canvas?.getContext?.('webgl2',{powerPreference:'default'})||canvas?.getContext?.('webgl',{powerPreference:'default'});
      if(!gl) return 'unavailable';
      const vendor=String(gl.getParameter(gl.VENDOR)||'unknown').slice(0,80);
      const renderer=String(gl.getParameter(gl.RENDERER)||'unknown').slice(0,120);
      const version=String(gl.getParameter(gl.VERSION)||'unknown').slice(0,80);
      return `${vendor} · ${renderer} · ${version}`;
    }catch(_){return 'unknown';}
  }
  function collectEnvironment(env=root){
    const nav=env.navigator||{};
    const width=Number(env.innerWidth)||0;
    const height=Number(env.innerHeight)||0;
    const dpr=Math.max(0.1,Math.min(8,Number(env.devicePixelRatio)||1));
    const cpu=Number(nav.hardwareConcurrency);
    const memory=Number(nav.deviceMemory);
    return {
      Captured:new Date().toISOString(),
      Browser:browserDescription(nav),
      Viewport:`${width||'?'}×${height||'?'}`,
      'Device pixel ratio':Number(dpr.toFixed(2)),
      Input:inputDescription(env),
      'Reduced motion':reducedMotion(env),
      'Logical CPU threads':Number.isFinite(cpu)&&cpu>0?Math.min(256,Math.round(cpu)):'unknown',
      'Reported device memory GiB':Number.isFinite(memory)&&memory>0?Math.min(128,memory):'unknown',
      WebGL:webglDescription(env)
    };
  }
  async function fetchBuildInfo(url='build-info.json',env=root){
    if(!env.fetch||!env.location) return null;
    try{
      const request=env.fetch(new URL(url,env.location.href),{cache:'no-store',credentials:'same-origin'}).then(async response=>{
        if(!response.ok) return null;
        const value=await response.json();
        return value&&typeof value==='object'?value:null;
      }).catch(()=>null);
      return await Promise.race([request,new Promise(resolve=>setTimeout(()=>resolve(null),900))]);
    }catch(_){return null;}
  }
  function buildSummary(info){
    if(!info) return null;
    const sha=info.sha256||info.sha||info.commit||info.version||info.build||null;
    const bytes=Number.isFinite(Number(info.bytes))?Number(info.bytes):null;
    const gzip=Number.isFinite(Number(info.gzip_bytes))?Number(info.gzip_bytes):null;
    if(!sha&&!bytes&&!gzip) return null;
    return `${sha||'unknown'}${bytes===null?'':` · ${bytes} bytes${gzip===null?'':` (${gzip} gzip)`}`}`;
  }
  function buildIssueBody({message,game,site,build,state={},environment={}}){
    const lines=[
      '## Player feedback','',message,'','---','',
      '<details>',`<summary>Automatic ${game} diagnostics</summary>`,'',
      'These bounded capability details were added automatically so the report can be reproduced. They exclude page URLs/query strings, cookies, account identity, geolocation, browsing history and the full User-Agent string.','',
      `- Game: **${game}** (\`${site}\`)`
    ];
    if(build) lines.push(`- Build: \`${String(build).replace(/`/g,"'")}\``);
    for(const [key,value] of Object.entries(state)){
      if(value===undefined||value===null||value==='') continue;
      lines.push(`- ${safeLabel(key)}: ${textValue(value)}`);
    }
    for(const [key,value] of Object.entries(environment)) lines.push(`- ${key}: ${textValue(value)}`);
    lines.push('','</details>');
    return lines.join('\n');
  }
  function buildIssueDraft({issueUrl=DEFAULT_ISSUE_URL,message,game,site,build,state={},environment={}}){
    const clean=String(message||'').trim();
    if(!clean) throw new TypeError('Feedback message is required.');
    const summary=clean.replace(/\s+/g,' ');
    const title=`[${game}] ${summary.slice(0,72)}${summary.length>72?'…':''}`;
    const body=buildIssueBody({message:clean,game,site,build,state,environment});
    const url=new URL(issueUrl);
    url.searchParams.set('title',title);
    url.searchParams.set('body',body);
    return {
      schema:'axioms-feedback-draft/v1',
      feedback:clean,
      game,site,build:build||null,
      state,environment,
      issue:{title,body,url:url.toString()}
    };
  }
  function buildIssueUrl(options){return buildIssueDraft(options).issue.url;}
  async function prepareFeedbackDraft(options){
    const env=options.env||root;
    const state=await Promise.resolve(options.getState?.()||{});
    let info=null;
    if(options.getBuild) info=await Promise.resolve(options.getBuild());
    else if(options.buildInfoUrl!==false) info=await fetchBuildInfo(options.buildInfoUrl||'build-info.json',env);
    const build=options.build||buildSummary(info);
    return buildIssueDraft({
      issueUrl:options.issueUrl||DEFAULT_ISSUE_URL,
      message:options.message,
      game:options.game,
      site:options.site,
      build,state,
      environment:collectEnvironment(env)
    });
  }
  async function prepareFeedback(options){return (await prepareFeedbackDraft(options)).issue.url;}
  function persistFeedbackDraft(draft,env=root){
    lastDraft=draft;
    try{env.sessionStorage?.setItem(DRAFT_KEY,JSON.stringify(draft));}catch(_){}
    return draft;
  }
  function getLastFeedbackDraft(env=root){
    if(lastDraft) return lastDraft;
    try{
      const raw=env.sessionStorage?.getItem(DRAFT_KEY);
      if(raw){
        const parsed=JSON.parse(raw);
        if(parsed&&parsed.schema==='axioms-feedback-draft/v1') return parsed;
      }
    }catch(_){}
    return null;
  }
  function installFeedbackButton(options){
    const env=options.env||root;
    const doc=env.document;
    if(!doc) throw new TypeError('A browser document is required.');
    if(!options.game||!options.site) throw new TypeError('game and site are required.');
    const id=options.id||'playerFeedbackBtn';
    if(doc.getElementById(id)) return doc.getElementById(id);
    const host=typeof options.host==='string'?doc.querySelector(options.host):options.host;
    if(!host) throw new Error('Feedback button host was not found.');
    const button=doc.createElement('button');
    button.id=id;
    button.type='button';
    button.className=options.className||'';
    button.textContent=options.label||'💬 Feedback';
    button.title=options.title||`Send feedback about ${options.game}`;
    button.setAttribute('aria-label',button.title);
    button.addEventListener('click',async()=>{
      const promptFn=options.prompt||env.prompt?.bind(env);
      if(!promptFn) return;
      const message=promptFn(options.promptText||'What happened, or what would you like to change?\n\nYou will get a chance to review it before submitting.');
      if(message===null||!String(message).trim()) return;
      const original=button.textContent;
      button.disabled=true;
      button.textContent=options.preparingLabel||'Preparing…';
      let draft=null;
      try{
        draft=await prepareFeedbackDraft({...options,message,env});
        persistFeedbackDraft(draft,env);
        if(options.navigate) await options.navigate(draft.issue.url,draft);
        else env.location.assign(draft.issue.url);
      }catch(error){
        button.title='Feedback draft saved locally; the filing target could not be opened.';
        if(options.onFilingError) options.onFilingError(error,draft);
        else env.console?.error?.('Feedback filing target failed; draft remains retrievable.',error);
      }finally{
        button.disabled=false;
        button.textContent=original;
      }
    });
    host.appendChild(button);
    return button;
  }
  return {collectEnvironment,fetchBuildInfo,buildSummary,buildIssueBody,buildIssueDraft,buildIssueUrl,prepareFeedbackDraft,prepareFeedback,persistFeedbackDraft,getLastFeedbackDraft,installFeedbackButton};
});
