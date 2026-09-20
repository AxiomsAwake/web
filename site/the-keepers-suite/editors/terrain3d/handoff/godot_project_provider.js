'use strict';
// Opaque native-project exchange adapter for the full Godot/Terrain3D application.
(() => {
  function base64(bytes){let text='';for(let i=0;i<bytes.length;i+=8192)text+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(text);}
  window.AxiomsGodotProjectProvider = function(configuration){
    const root=new URL('.',location.href),entry=new URL(configuration.entry,root),back=new URL(root);
    if(entry.origin!==root.origin || !entry.pathname.startsWith(root.pathname) || entry.pathname===root.pathname || !entry.pathname.endsWith('/') || entry.search || entry.hash)throw new Error('Editor must live in a dedicated owned subfolder');
    if(!/^[a-z][a-z0-9-]{0,63}$/.test(configuration.workspace))throw new Error('Invalid return workspace');
    back.searchParams.set('workspace',configuration.workspace);
    const key=entry.pathname;
    return Object.freeze({
      open(){const url=new URL(entry);url.hash=new URLSearchParams({return:back.href,context:configuration.workspace,session:crypto.randomUUID()}).toString();location.assign(url.href);},
      async summary(){
        const saved=await AxiomsProjectIO.summary(key);
        if(!saved)return {has_project:false,format:'godot-native-project'};
        const preview=saved.preview?base64(new Uint8Array(saved.preview)):'';
        return {has_project:true,format:'godot-native-project',bytes:saved.bytes,sha256:saved.receipt?.sha256||'',preview};
      },
      async download(){
        const bytes=await AxiomsProjectIO.read(key);
        if(!bytes)throw new Error('Save a native project in the editor first.');
        const url=URL.createObjectURL(new Blob([bytes],{type:'application/zip'}));
        const link=document.createElement('a');link.href=url;link.download='terrain-project.zip';link.click();
        setTimeout(()=>URL.revokeObjectURL(url),30000);
      },
    });
  };
})();
