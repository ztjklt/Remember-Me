const test=require('node:test'),assert=require('node:assert/strict');
const M=require('../nature/garden-v21/scene-model.js'),G=require('./camera.js'),S=require('./botanical-v21.js');
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-7,`${a} vs ${b}`);
test('scene rotation covers the library, excludes the previous scene and handles random endpoints',()=>{
  assert.equal(M.scenes.length,4);assert.ok(M.scenes.some(s=>s.id==='night'));
  for(const previous of M.scenes.map(s=>s.id)){
    const seen=new Set();for(let i=0;i<=100;i++){const next=M.next(previous,()=>i/100);assert.notEqual(next,previous);seen.add(next);}
    assert.equal(seen.size,3);
  }
});
test('the landscape and foreground project the same point through the whole camera trajectory',()=>{
  for(const width of [320,390,520]){
    const stage={left:21,top:147,width,height:width*420/360},scene={left:0,top:0,width:width+42,height:844},m=M.metrics(stage,scene);
    const follow=G.interpolate({x:0,y:0,z:1},G.focus({x:90,y:252},2.1),{x:90,y:252});
    for(let i=0;i<=60;i++){const c=follow(i/60),p={x:97,y:301},screen=G.project(p,c),base={x:stage.left+p.x*m.sx,y:stage.top+p.y*m.sy};
      near(scene.left+m.ox+(base.x-scene.left-m.ox)*c.z+c.x*m.sx,stage.left+screen.x*m.sx);
      near(scene.top+m.oy+(base.y-scene.top-m.oy)*c.z+c.y*m.sy,stage.top+screen.y*m.sy);
    }
  }
});
test('panning cannot reveal an empty background edge at any supported zoom',()=>{
  const m=M.metrics({left:0,top:190,width:390,height:455},{left:0,top:0,width:390,height:844});
  for(const z of [1,1.2,2,4.8])for(const x of [-9999,0,9999])for(const y of [-9999,0,9999]){
    const c=M.constrain({x,y,z},m),left=m.ox+(-27-m.ox)*c.z+c.x*m.sx,top=m.oy+(-27-m.oy)*c.z+c.y*m.sy;
    const right=m.ox+(m.w+27-m.ox)*c.z+c.x*m.sx,bottom=m.oy+(m.h+27-m.oy)*c.z+c.y*m.sy;
    assert.ok(left<1e-7&&top<1e-7&&right>=m.w-1e-7&&bottom>=m.h-1e-7);
  }
});
test('photographic stem joins both endpoints without flattening its leaves, including a mirrored view',()=>{
  for(const mirror of [false,true])for(const tip of [{x:154,y:140},{x:150,y:311},{x:244,y:319}]){
    const base={x:176,y:478},m=S.fit(tip,base,mirror),project=p=>{const x=mirror?S.photo.width-p.x:p.x;return{x:m.a*x+m.c*p.y+m.e,y:m.b*x+m.d*p.y+m.f};};
    const a=project(S.photo.tip),b=project(S.photo.base);near(a.x,tip.x);near(a.y,tip.y);near(b.x,base.x);near(b.y,base.y);
    near(Math.hypot(m.a,m.b),Math.hypot(m.c,m.d));near(m.a*m.c+m.b*m.d,0);
  }
});
