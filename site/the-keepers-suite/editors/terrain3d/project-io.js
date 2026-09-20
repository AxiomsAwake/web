'use strict';
// Keep native source opaque. A preview is never used to reconstruct the master.
window.AxiomsProjectIO=(()=>{
  const MAX_BYTES=512*1024*1024,MAX_FILES=12000,DATABASE='axioms-full-editor-projects-v1';
  const KEY=new URL('.',location.href).pathname;
  const sha=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
  function safe(path){return typeof path==='string' && path.length<=1024 && !/[\\\u0000-\u001f:]/.test(path) && !path.startsWith('/') && !path.split('/').some(x=>!x || x==='.' || x==='..');}
  async function decode(bytes,manifest){
    if(!(bytes instanceof Uint8Array) || bytes.byteLength>MAX_BYTES)throw new Error('Native project archive exceeds the transfer budget');
    let total=0,count=0;const seen=new Set();
    const contents=fflate.unzipSync(bytes,{filter(entry){
      const directory=entry.name.endsWith('/'),name=directory?entry.name.slice(0,-1):entry.name;
      if(!safe(name) || /(^|\/)(\.git|\.godot|\.env(?:\..*)?)(\/|$)/.test(name))throw new Error('Unsafe, generated or secret project path: '+entry.name);
      const key=entry.name.toLowerCase();if(seen.has(key))throw new Error('Duplicate or case-colliding project path: '+entry.name);seen.add(key);
      if(directory)return false;
      if(!Number.isSafeInteger(entry.originalSize) || entry.originalSize<0)throw new Error('Invalid ZIP member size');
      total+=entry.originalSize;if(++count>MAX_FILES || total>MAX_BYTES)throw new Error('Expanded project exceeds the import budget');return true;
    }});
    if(!contents['project.godot'])throw new Error('The ZIP must contain project.godot at its root');
    let entry='res://world.tscn';
    if(contents['studio-project.json'])entry=JSON.parse(new TextDecoder().decode(contents['studio-project.json'])).entry_scene;
    if(typeof entry!=='string' || !entry.startsWith('res://') || !safe(entry.slice(6)) || !contents[entry.slice(6)])throw new Error('Native project entry scene is missing or invalid');
    // Native tool upgrades are deliberate, not executable dependencies smuggled
    // into a returned terrain archive. Keep rejected ZIPs unchanged for migration.
    for(const item of manifest.files){
      if(!item.path.startsWith('addons/terrain_3d/') && !item.path.startsWith('addons/axioms_project_exchange/'))continue;
      const file=contents[item.path];
      if(!file || file.byteLength!==item.bytes || await sha(file)!==item.sha256)throw new Error('Different editor dependency: '+item.path+'. Use its matching editor or migrate explicitly.');
    }
    const config=new TextDecoder().decode(contents['project.godot']);
    if(!config.includes('res://addons/terrain_3d/plugin.cfg') || !config.includes('res://addons/axioms_project_exchange/plugin.cfg'))throw new Error('Retain the native terrain and project-exchange plugins');
    return contents;
  }
  function database(){return new Promise((resolve,reject)=>{
    const request=indexedDB.open(DATABASE,1);request.onupgradeneeded=()=>request.result.createObjectStore('projects');
    request.onerror=()=>reject(request.error);request.onsuccess=()=>resolve(request.result);
  });}
  async function record(key=KEY){
    const db=await database();try{return await new Promise((resolve,reject)=>{
      const request=db.transaction('projects').objectStore('projects').get(key);
      request.onsuccess=()=>resolve(request.result || null);request.onerror=()=>reject(request.error);
    });}finally{db.close();}
  }
  async function read(key=KEY){const saved=await record(key);return saved instanceof Uint8Array?saved:(saved?.bytes || null);}
  async function summary(key=KEY){const saved=await record(key);if(!saved)return null;return {bytes:(saved.bytes || saved).byteLength,receipt:saved.receipt || null,preview:saved.preview || null};}
  async function stage(bytes,receipt=null,preview=null){
    if(!(bytes instanceof Uint8Array) || bytes.byteLength>MAX_BYTES)throw new Error('Invalid native master');
    const db=await database();try{await new Promise((resolve,reject)=>{
      const transaction=db.transaction('projects','readwrite');transaction.objectStore('projects').put({bytes,receipt,preview},KEY);
      transaction.oncomplete=resolve;transaction.onerror=()=>reject(transaction.error);transaction.onabort=()=>reject(transaction.error || new Error('Project storage was canceled'));
    });}finally{db.close();}
  }
  async function clear(){const db=await database();try{await new Promise((resolve,reject)=>{
    const transaction=db.transaction('projects','readwrite');transaction.objectStore('projects').delete(KEY);
    transaction.oncomplete=resolve;transaction.onerror=()=>reject(transaction.error);transaction.onabort=()=>reject(transaction.error);
  });}finally{db.close();}}
  return Object.freeze({decode,read,stage,clear,summary,sha,safe,MAX_BYTES});
})();
