/* Browser-local viewing and shortlist. No accounts, uploads or background engine launch. */
(()=>{'use strict';
 const items=window.inspirationData.items,$=id=>document.getElementById(id),storage='axiomsawake.engine-inspiration.saved.v1';
 let saved=new Set();try{saved=new Set(JSON.parse(localStorage.getItem(storage)||'[]').filter(x=>typeof x==='string'));}catch{}
 let selected=items[0],onlySaved=false,visible=items;
 const el=(name,text,cls)=>{const n=document.createElement(name);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 const poster=r=>r.visual.poster||(r.visual.type==='youtube'?'https://i.ytimg.com/vi/'+r.visual.videoId+'/hqdefault.jpg':null);
 for(const name of [...new Set(items.map(r=>r.engine))].sort()){$('engine').add(new Option(name,name));}
 for(const name of [...new Set(items.map(r=>r.category||'More ideas'))].sort()){$('category').add(new Option(name,name));}
 $('count').textContent=items.length+' visual references · '+new Set(items.map(r=>r.engine)).size+' engines';
 function remember(){try{localStorage.setItem(storage,JSON.stringify([...saved]));}catch{}}
 function choose(r){
  selected=r;const stage=$('stage');stage.replaceChildren();
  const p=poster(r);
  if(p){const img=el('img');img.src=p;img.alt=r.title+' — upstream preview';img.referrerPolicy='no-referrer';stage.append(img);}
  else{const panel=el('div',undefined,'no-poster');const copy=el('div');copy.append(el('span',r.engine),el('strong',r.title));panel.append(copy);stage.append(panel);}
  stage.append(el('span',r.visual.type==='interactive'?'Interactive reference':'Video reference','media-label'));
  const overlay=el('div',undefined,'start'),start=el('button',r.visual.type==='interactive'?'Explore this demo ↗':'▶ Watch the showcase');start.type='button';
  start.addEventListener('click',()=>{
   if(r.visual.type==='interactive'){window.open(r.visual.url,'_blank','noopener,noreferrer');return;}
   stage.replaceChildren();
   if(r.visual.type==='youtube'){const frame=el('iframe');frame.title=r.title;frame.src='https://www.youtube-nocookie.com/embed/'+r.visual.videoId+'?autoplay=1&rel=0';frame.allow='autoplay; encrypted-media; fullscreen; picture-in-picture';frame.allowFullscreen=true;frame.referrerPolicy='strict-origin-when-cross-origin';stage.append(frame);}
   else{const video=el('video');video.src=r.visual.url;video.controls=true;video.playsInline=true;video.preload='metadata';stage.append(video);video.play().catch(()=>{});}
  });overlay.append(start);stage.append(overlay);
  for(const [id,value]of Object.entries({'engine-label':r.engine+(r.eraLabel?' · '+r.eraLabel:''),title:r.title,capability:r.capability,why:r.whyInteresting,observe:r.observe,question:r.adoption.question,route:r.adoption.route,status:r.adoption.status.includes('candidate-route')?'Existing Godot route found · not tested':'Adoption question · not tested',rights:r.rightsNote}))$(id).textContent=value;
  $('original').href=r.visual.url;$('reference-kind').textContent='Upstream reference · '+(r.visual.type==='interactive'?'opens separately':r.visual.type==='youtube'?'YouTube':'native video');
  $('sources').replaceChildren(...r.sources.map(s=>{const li=el('li'),a=el('a',s.title);a.href=s.url;a.target='_blank';a.rel='noopener noreferrer';li.append(a);return li;}));
  syncSave();renderList();
 }
 function syncSave(){const kept=saved.has(selected.id);$('save').textContent=kept?'✓ Saved for Godot':'Save idea';$('save').setAttribute('aria-pressed',String(kept));}
 function renderList(){const q=$('search').value.toLowerCase().trim(),engine=$('engine').value,category=$('category').value;
  visible=items.filter(r=>(!engine||r.engine===engine)&&(!category||(r.category||'More ideas')===category)&&(!onlySaved||saved.has(r.id))&&(!q||[r.engine,r.title,r.capability,r.whyInteresting,r.adoption.question].join(' ').toLowerCase().includes(q)));
  $('shown').textContent=visible.length+(visible.length===1?' example':' examples');
  $('list').replaceChildren(...visible.map(r=>{const b=el('button',undefined,'item'+(r.id===selected.id?' active':''));b.type='button';b.setAttribute('aria-label',r.engine+': '+r.title);b.setAttribute('aria-current',String(r.id===selected.id));const p=poster(r);if(p){const image=el('img',undefined,'thumb');image.src=p;image.alt='';image.loading='lazy';image.referrerPolicy='no-referrer';b.append(image);}else b.append(el('span',r.visual.type==='interactive'?'LIVE DEMO':'PLAY VIDEO','thumb thumb-label'));const copy=el('span');copy.append(el('span',r.engine+(saved.has(r.id)?' · saved':''),'engine'),el('strong',r.title));if(r.eraLabel)copy.append(el('span',r.eraLabel,'era'));b.append(copy);b.addEventListener('click',()=>choose(r));return b;}));
  if(!visible.length)$('list').append(el('p','No matching ideas. Try another filter.','empty'));
 }
 $('save').addEventListener('click',()=>{saved.has(selected.id)?saved.delete(selected.id):saved.add(selected.id);remember();syncSave();renderList();});
 function filter(){renderList();if(visible.length&&!visible.some(r=>r.id===selected.id))choose(visible[0]);}
 $('kept').addEventListener('click',()=>{onlySaved=!onlySaved;$('kept').setAttribute('aria-pressed',String(onlySaved));filter();});
 for(const id of ['search','engine','category'])$(id).addEventListener(id==='search'?'input':'change',filter);
 $('next').addEventListener('click',()=>{if(visible.length)choose(visible[(visible.findIndex(r=>r.id===selected.id)+1)%visible.length]);});
 choose(items.find(r=>r.id==='playcanvas-relightable-courtyard')||selected);
})();
