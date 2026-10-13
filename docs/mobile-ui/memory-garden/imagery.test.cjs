const test=require('node:test'),assert=require('node:assert/strict');
const M=require('./imagery-model.js'),G=require('./geometry.js');
const {points,episodes}=require('./data.js');
const p=points[0],q=points.find(p=>p.episode==='E01');
const memoryStorage=()=>{let text;return {getItem:()=>text,setItem:(key,value)=>{text=value;}};};
test('A preview draft does not save a choice; adoption waits for the right decoded image',()=>{
  const storage=memoryStorage(),store=M.createStore(points,episodes,storage);
  let draft=M.createDraft(p,episodes);
  assert.equal(M.canAdopt(draft,p,episodes),false);
  draft=M.preview(draft);assert.equal(M.canAdopt(draft,p,episodes),false);
  assert.equal(M.canAdopt(M.resolve(draft,{width:1024,height:1536}),p,episodes),false);
  assert.equal(M.canAdopt(M.resolve(draft,{width:1536,height:1024,error:true}),p,episodes),false);
  draft=M.resolve(draft,{width:1536,height:1024});
  assert.equal(M.canAdopt(draft,p,episodes),true);
  assert.equal(M.canAdopt(draft,q,episodes),false);
  assert.equal(M.canAdopt({...draft,asset:'library'},p,episodes),false);
  assert.equal(storage.getItem(),undefined);assert.equal(store.get(p).status,'shared');
});
test('Adopt and hide are isolated per point and survive a reload; hiding is reversible',()=>{
  const storage=memoryStorage(),store=M.createStore(points,episodes,storage);
  assert.equal(store.adopt(p).persisted,true);store.hide(q);
  const restored=M.createStore(points,episodes,storage);
  assert.equal(restored.get(p).status,'adopted');assert.equal(restored.get(q).hidden,true);
  assert.equal(restored.get(points[2]).status,'shared');
  restored.adopt(q);assert.equal(restored.get(q).hidden,false);
});
test('A changed quote invalidates adoption but does not unhide a hidden image',()=>{
  const store=M.createStore(points,episodes,memoryStorage());store.hide(p);
  const revised={...p,quote:p.quote+' 补充过的文字'};
  assert.equal(store.get(revised).status,'stale');assert.equal(store.get(revised).hidden,true);
  const old=M.resolve(M.preview(M.createDraft(p,episodes)),{width:1536,height:1024});
  assert.equal(M.canAdopt(old,revised,episodes),false);
});
test('Storage denial preserves this visit without claiming a durable save',()=>{
  const storage={getItem:()=>null,setItem:()=>{throw Error('quota');}};
  const store=M.createStore(points,episodes,storage),result=store.adopt(p);
  assert.equal(result.persisted,false);assert.equal(store.isWritable(),false);assert.equal(store.get(p).status,'adopted');
});
test('Corrupt or foreign saved image records cannot substitute another story or arbitrary image URL',()=>{
  const corrupt=M.createStore(points,episodes,{getItem:()=>'{broken'});assert.equal(corrupt.get(p).status,'shared');
  const payload={version:1,records:{[p.id]:{episode:'E01',asset:'https://invalid.example/image',status:'adopted',style:M.STYLE,source:M.sourceKey(p)}}};
  const foreign=M.createStore(points,episodes,{getItem:()=>JSON.stringify(payload)});assert.equal(foreign.get(p).status,'shared');
});
test('Natural network links connect every point in its own story without inventing cross-story links',()=>{
  for(const layout of ['flower','constellation']){
  const nodes=points.map((p,i)=>({...p,layoutIndex:i})),edges=G.storyEdges(nodes,layout);
  assert.equal(edges.length,points.length-Object.keys(episodes).length);
  for(const ep of Object.keys(episodes)){
    const ids=nodes.filter(n=>n.episode===ep).map(n=>n.id),seen=new Set([ids[0]]),links=edges.filter(e=>e.episode===ep);
    assert.equal(links.length,ids.length-1);
    for(const e of links){assert.ok(ids.includes(e.from)&&ids.includes(e.to));for(const endpoint of [e.a,e.b]){const pos=G.point(endpoint.layoutIndex,layout);assert.equal(endpoint.x,pos.x);assert.equal(endpoint.y,pos.y);}}
    for(let i=0;i<ids.length;i++)for(const e of links){if(seen.has(e.from))seen.add(e.to);if(seen.has(e.to))seen.add(e.from);}
    assert.equal(seen.size,ids.length);
  }
  assert.deepEqual(G.storyEdges(nodes.filter(n=>n.id===p.id),layout),[]);
  }
});
