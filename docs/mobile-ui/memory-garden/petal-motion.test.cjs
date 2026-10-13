const {test}=require('node:test');
const assert=require('node:assert/strict');
const M=require('./petal-motion.js');
const project=(m,p)=>({x:m.a*p.x+m.c*p.y+m.e,y:m.b*p.x+m.d*p.y+m.f});
test('Selected petal retains exact screen coordinates at both handoff boundaries',()=>{
  const from={a:-1.2,b:.8,c:-.8,d:-1.2,e:260,f:430},to={a:5,b:0,c:0,d:18,e:180,f:1250},pivot={x:0,y:-30};
  const track=M.track(from,to,pivot);
  for(const p of [{x:-7,y:-1},{x:31,y:-38},{x:-4,y:-60}])for(const [t,m] of [[0,from],[1,to]]){
    const a=project(track(t),p),b=project(m,p);assert.ok(Math.hypot(a.x-b.x,a.y-b.y)<1e-8);
  }
});
test('Unfolding does not collapse opposite-facing petals and pivot moves without a detour',()=>{
  for(const angle of [-176,-82,8,151,178]){
    const a=angle*Math.PI/180,from={a:Math.cos(a)*2,b:Math.sin(a)*2,c:-Math.sin(a)*2,d:Math.cos(a)*2,e:280,f:450},to={a:5,b:0,c:0,d:17,e:180,f:1250},pivot={x:0,y:-30};
    const track=M.track(from,to,pivot),end=project(to,pivot);let distance=Infinity;
    for(let i=0;i<=100;i++){const m=track(i/100),p=project(m,pivot),next=Math.hypot(p.x-end.x,p.y-end.y);assert.ok(m.a*m.d-m.b*m.c>0);assert.ok(next<=distance+1e-7);distance=next;}
  }
});
test('Both directions respond immediately and arrive at the original geometry',()=>{
  const a={a:2,b:0,c:0,d:2,e:40,f:260},b={a:6,b:0,c:0,d:20,e:180,f:1300},p={x:3,y:-32};
  const f=M.track(a,b,p),r=M.track(b,a,p);
  for(const [curve,start,end] of [[f,a,b],[r,b,a]]){
    const origin=project(start,p),destination=project(end,p),early=project(curve(.2),p);
    // In the first fifth of the transition, the camera has covered over half
    // the focus distance, instead of waiting behind the previous smoothstep.
    assert.ok(Math.hypot(early.x-origin.x,early.y-origin.y)/Math.hypot(destination.x-origin.x,destination.y-origin.y)>.5);
    for(const k of ['a','b','c','d','e','f'])assert.ok(Math.abs(curve(1)[k]-end[k])<1e-8);
  }
});
test('Petal and flower camera use the same focus and magnification cadence',()=>{
  const C=require('./camera.js'),p={x:0,y:0},from={a:1,b:0,c:0,d:1,e:40,f:100},to={a:3,b:0,c:0,d:3,e:180,f:210};
  const petal=M.track(from,to,p),flower=C.interpolate({x:-140,y:-110,z:1},{x:0,y:0,z:3},C.center);
  for(const t of [.01,.1,.25,.5,.75,1]){
    const m=petal(t),c=flower(t);assert.ok(Math.abs(m.a-c.z)<1e-8);
    assert.ok(Math.abs(m.e-(180+c.x))<1e-8);assert.ok(Math.abs(m.f-(210+c.y))<1e-8);
  }
});
