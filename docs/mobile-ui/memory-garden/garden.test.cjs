const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {categories,episodes,points}=require('./data.js');
const {constrain,zoomAt,pinch,point,branches,storyEdges}=require('./geometry.js');
const almost=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,`${a} differs from ${b}`);

test('Every displayed quote is present in its own original fictional script',()=>{
  assert.equal(new Set(points.map(p=>p.id)).size,15);
  for(const p of points){
    const script=fs.readFileSync(path.join(__dirname,'sources',`${p.episode}.txt`),'utf8');
    assert.ok(script.includes(p.quote),`${p.id}: quote must belong to ${p.episode}`);
    assert.ok(categories.some(c=>c.id===p.category));
    assert.ok(episodes[p.episode]);
  }
});
test('All images have the same actual PNG dimensions, and every story has playable MP3 bytes',()=>{
  for(const [id,ep] of Object.entries(episodes)){
    const png=fs.readFileSync(path.join(__dirname,'images',ep.image+'.png'));
    assert.deepEqual([...png.subarray(0,8)],[137,80,78,71,13,10,26,10]);
    assert.equal(png.readUInt32BE(16),1536);assert.equal(png.readUInt32BE(20),1024);
    assert.ok(fs.statSync(path.join(__dirname,'audio',id+'.mp3')).size>100000);
  }
});
test('Zoom keeps the touched location stationary away from clamp boundaries',()=>{
  const c={z:1.5,x:12,y:-15},a={x:210,y:160},n=zoomAt(c,2.3,a);
  almost((a.x-180-c.x)/c.z,(a.x-180-n.x)/n.z);
  almost((a.y-200-c.y)/c.z,(a.y-200-n.y)/n.z);
});
test('Pinch combines scale and midpoint translation without jumping',()=>{
  const c={z:1.4,x:0,y:0},start=[{x:140,y:200},{x:220,y:200}];
  const moved=[{x:130,y:210},{x:250,y:210}],n=pinch(c,start,moved);
  almost(n.z,2.1);almost(n.x,10);almost(n.y,10);
  assert.deepEqual(pinch(c,start,start),c);
});
test('Zoom limits, one-finger pan bounds and coincident pointers remain finite',()=>{
  assert.deepEqual(constrain({z:.1,x:999,y:-999}),{z:1,x:0,y:0});
  const n=constrain({z:20,x:99999,y:-99999});almost(n.z,2.8);almost(n.x,324);almost(n.y,-360);
  const same=[{x:180,y:200},{x:180,y:200}];
  assert.ok(Object.values(pinch({z:1,x:0,y:0},same,same)).every(Number.isFinite));
});
test('Flower and constellation hit targets stay separated and inside the smallest 320px phone layout',()=>{
  for(const layout of ['flower','constellation']){
  const locations=points.map((_,i)=>point(i,layout));
  // The stage has 269 CSS px after gutters and a 15px scrollbar. Buttons have circular hit regions.
  for(let i=0;i<locations.length;i++)for(let j=i+1;j<locations.length;j++){
    const dx=Math.abs(locations[i].x-locations[j].x)*269/360;
    const dy=Math.abs(locations[i].y-locations[j].y)*269/360;
    assert.ok(Math.hypot(dx,dy)>=48,`${layout}: circular hit regions overlap: ${i} and ${j}`);
  }
  for(const p of locations){const margin=24*360/269;assert.ok(p.x>=margin&&p.x<=360-margin&&p.y>=margin&&p.y<=400-margin);}
  }
});

test('Growing to 302 memories keeps bounded branches, complete coverage and stable old positions',()=>{
  const many=Array.from({length:302},(_,i)=>({id:`growth-${i}`,episode:`story-${Math.floor(i/7)}`}));
  const before=branches(many.slice(0,29)),after=branches(many);
  assert.equal(after.length,21);
  assert.deepEqual(after.flatMap(b=>b.points.map(p=>p.id)),many.map(p=>p.id));
  for(const branch of after){
    assert.ok(branch.points.length<=15);
    assert.ok(branch.points.every(p=>Object.values(point(p.layoutIndex)).every(Number.isFinite)));
    for(const edge of storyEdges(branch.points))assert.equal(edge.a.episode,edge.b.episode);
  }
  const slots=group=>new Map(group.flatMap(b=>b.points.map(p=>[p.id,[b.id,p.layoutIndex]])));
  const oldSlots=slots(before),newSlots=slots(after);
  for(const [id,slot] of oldSlots)assert.deepEqual(newSlots.get(id),slot);
  const filtered=branches(many,p=>Number(p.id.split('-')[1])%17===0);
  for(const [id,slot] of slots(filtered))assert.deepEqual(newSlots.get(id),slot);
  assert.deepEqual(branches([]),[]);
  assert.deepEqual(branches(many,()=>false),[]);
});
