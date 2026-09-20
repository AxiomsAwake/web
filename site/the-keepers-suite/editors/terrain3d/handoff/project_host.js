'use strict';
// Thin application handoff. Providers own native formats; no terrain operations here.
(() => {
  const providers = new Map(), states = new Map(), controls = new Map();
  function requireProvider(id){const p=providers.get(id);if(!p)throw new Error('Editor provider is not configured');return p;}
  function failed(id,error){states.set(id,{ready:false,has_project:false,error:String(error?.message||error)});}
  async function refresh(id){try{states.set(id,{ready:true,...await requireProvider(id).summary()});}catch(error){failed(id,error);}}
  window.AxiomsNativeProjects=Object.freeze({
    register(id,provider){
      if(!/^[a-z][a-z0-9-]{0,63}$/.test(id)||providers.has(id))throw new Error('Invalid or duplicate editor provider');
      for(const key of ['open','summary','download'])if(typeof provider[key]!=='function')throw new Error('Editor provider lacks '+key);
      providers.set(id,provider);refresh(id);
    },
    state(id){return JSON.stringify(states.get(id)||{ready:false,error:'Editor integration is not available in this package.'});},
    refresh,
    open(id){try{requireProvider(id).open();}catch(error){failed(id,error);}},
    async download(id){try{await requireProvider(id).download();}catch(error){failed(id,error);}},
    noteControls(id,json){const value=JSON.parse(json);if(providers.has(id)&&Array.isArray(value))controls.set(id,value);},
    getControls(id){return structuredClone(controls.get(id)||[]);},
  });
})();
