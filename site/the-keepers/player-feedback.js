/* Shared browser player-feedback composer. No credentials; opens a public issue draft for review. */
(function(root,factory){
  const api=factory(root);
  if(typeof module==='object'&&module.exports) module.exports=api;
  else root.AxiomsPlayerFeedback=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(root){
  'use strict';
  const DEFAULT_ISSUE_URL='https://github.com/AxiomsAwake/web/issues/new';

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
    if((nav.maxTouchPoints||0)>0) parts.push(`touch (${nav.maxTouchPoints})`);
    try{parts.push(env.matchMedia?.('(pointer: coarse)')?.matches?'coarse pointer':'fine pointer');}catch(_){}
    return parts.length?parts.join(', '):'unknown';
  }
  function collectEnvironment(env=root){
    const nav=env.navigator||{};
    const scr=env.screen||{};
    let orientation='unknown';
    try{orientation=scr.orientation?.type||(env.matchMedia?.('(orientation: portrait)')?.matches?'portrait':'landscape');}catch(_){}
    return {
      Page: env.location?.href||'unknown',
      Captured: new Date().toISOString(),
      Viewport: `${env.innerWidth||'?'}×${env.innerHeight||'?'} @ ${env.devicePixelRatio||1}x DPR`,
      Screen: `${scr.width||'?'}×${scr.height||'?'} · ${orientation}`,
      Input: inputDescription(env),
      Language: nav.language||'unknown',
      Online: nav.onLine===false?'no':'yes',
      Hardware: `${nav.hardwareConcurrency||'unknown'} logical CPU threads${nav.deviceMemory?` · ${nav.deviceMemory} GiB reported memory`:''}`,
      'User agent': nav.userAgent||'unknown'
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
      'These details were added automatically so the report can be reproduced. They contain game/device state, not account credentials or cookies.','',
      `- Game: **${game}** (\`${site}\`)`
    ];
    if(build) lines.push(`- Build: \`${String(build).replace(/`/g,"'")}\``);
    for(const [key,value] of Object.entries(state)){
      if(value===undefined||value===null||value==='') continue;
      lines.push(`- ${safeLabel(key)}: ${textValue(value)}`);
    }
    for(const [key,value] of Object.entries(environment)){
      lines.push(`- ${key}: ${key==='User agent'?`\`${textValue(value).replace(/`/g,"'")}\``:textValue(value)}`);
    }
    lines.push('','</details>');
    return lines.join('\n');
  }
  function buildIssueUrl({issueUrl=DEFAULT_ISSUE_URL,message,game,site,build,state,environment}){
    const clean=String(message||'').trim();
    if(!clean) throw new TypeError('Feedback message is required.');
    const summary=clean.replace(/\s+/g,' ');
    const url=new URL(issueUrl);
    url.searchParams.set('title',`[${game}] ${summary.slice(0,72)}${summary.length>72?'…':''}`);
    url.searchParams.set('body',buildIssueBody({message:clean,game,site,build,state,environment}));
    return url.toString();
  }
  async function prepareFeedback(options){
    const env=options.env||root;
    const state=await Promise.resolve(options.getState?.()||{});
    let info=null;
    if(options.getBuild) info=await Promise.resolve(options.getBuild());
    else if(options.buildInfoUrl!==false) info=await fetchBuildInfo(options.buildInfoUrl||'build-info.json',env);
    const build=options.build||buildSummary(info);
    return buildIssueUrl({
      issueUrl:options.issueUrl||DEFAULT_ISSUE_URL,
      message:options.message,
      game:options.game,
      site:options.site,
      build,
      state,
      environment:collectEnvironment(env)
    });
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
      try{
        const url=await prepareFeedback({...options,message,env});
        if(options.navigate) options.navigate(url);
        else env.location.assign(url);
      }finally{
        button.disabled=false;
        button.textContent=original;
      }
    });
    host.appendChild(button);
    return button;
  }
  return {collectEnvironment,fetchBuildInfo,buildSummary,buildIssueBody,buildIssueUrl,prepareFeedback,installFeedbackButton};
});
