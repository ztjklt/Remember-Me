/* Local demo choices only. A preview cannot submit a model request or grant consent. */
(function(root){
  const STYLE='remember-me-reverie-v1',KEY='remember-me.imagery-demo.v1';
  function sourceKey(p){
    // Exact source comparison, not a security hash. Demo source text is fictional.
    return JSON.stringify([p.episode,p.quote]);
  }
  function createStore(points,episodes,storage){
    let records={},writable=true;
    try{const data=JSON.parse(storage?.getItem(KEY)||'{}');
      if(data.version===1&&data.records&&typeof data.records==='object'){
        for(const p of points){const r=data.records[p.id];
          if(r&&r.episode===p.episode&&r.asset===episodes[p.episode].image&&r.style===STYLE&&
            ['adopted','hidden'].includes(r.status)&&typeof r.source==='string')
            records[p.id]={episode:r.episode,asset:r.asset,style:r.style,status:r.status,source:r.source};
        }
      }
    }catch{writable=false;}
    function save(){try{if(!storage)throw Error('storage unavailable');storage.setItem(KEY,JSON.stringify({version:1,records}));writable=true;return true;}catch{writable=false;return false;}}
    function get(p){const r=records[p.id];return r?{...r,hidden:r.status==='hidden',status:r.source===sourceKey(p)?r.status:'stale'}:{status:'shared',hidden:false};}
    function write(p,status){records[p.id]={episode:p.episode,asset:episodes[p.episode].image,style:STYLE,source:sourceKey(p),status};return {record:get(p),persisted:save()};}
    return {get,adopt:p=>write(p,'adopted'),hide:p=>write(p,'hidden'),isWritable:()=>writable};
  }
  function createDraft(p,episodes){return {memoryId:p.id,episode:p.episode,source:sourceKey(p),asset:episodes[p.episode].image,style:STYLE,step:'context',ready:false};}
  function preview(draft){return {...draft,step:'preview',ready:false};}
  function resolve(draft,{width,height,error=false}){return {...draft,ready:!error&&width===1536&&height===1024,error:error||width!==1536||height!==1024};}
  function canAdopt(draft,p,episodes){return draft.step==='preview'&&draft.ready===true&&draft.memoryId===p.id&&draft.episode===p.episode&&draft.asset===episodes[p.episode]?.image&&draft.source===sourceKey(p)&&draft.style===STYLE;}
  const api={STYLE,KEY,createStore,createDraft,preview,resolve,canAdopt,sourceKey};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.MemoryImageryModel=api;
})(typeof window==='undefined'?{}:window);
