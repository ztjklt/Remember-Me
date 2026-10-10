const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('./camera.js');
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-8, `${a} != ${b}`);
test('All flowers approach the focus monotonically, without a detour or zoom-out',()=>{
  for(const anchor of [{x:190.8,y:105},{x:90,y:252},{x:277.2,y:294}]){
    const start={x:0,y:0,z:1},end=C.focus(anchor,2),f=C.interpolate(start,end,anchor);
    const destination=C.project(anchor,end);let previous=Infinity,zoom=1;
    for(let i=0;i<=120;i++){
      const pose=f(i/120),point=C.project(anchor,pose),distance=Math.hypot(point.x-destination.x,point.y-destination.y);
      assert.ok(distance<=previous+1e-8); assert.ok(pose.z>=zoom-1e-8);
      previous=distance;zoom=pose.z;
    }
    assert.deepEqual(f(0),start);assert.deepEqual(f(1),end);
  }
});
test('Camera projection applies one spatial transform to flowers and branches',()=>{
  const pose={x:-83,y:56,z:2.3},a={x:80,y:42},b={x:270,y:370};
  const pa=C.project(a,pose),pb=C.project(b,pose);
  near(pb.x-pa.x,(b.x-a.x)*pose.z);near(pb.y-pa.y,(b.y-a.y)*pose.z);
  const restored=C.unproject(pa,pose);near(restored.x,a.x);near(restored.y,a.y);
});
test('An interrupted journey resumes exactly from the current pose, including on return',()=>{
  const anchor={x:90,y:252},home={x:27,y:-33,z:1.4},end=C.focus(anchor,2.1);
  const halfway=C.interpolate(home,end,anchor)(.37),back=C.interpolate(halfway,home,anchor);
  assert.deepEqual(back(0),halfway);assert.deepEqual(back(1),home);
});
test('Pinch and wheel retain the touched world point in the 360 by 420 viewport',()=>{
  const pose={x:15,y:-22,z:1.5},point={x:80,y:260},world=C.unproject(point,pose);
  const zoom=C.zoomAt(pose,2.2,point),after=C.project(world,zoom);near(after.x,point.x);near(after.y,point.y);
  const start=[{x:100,y:100},{x:200,y:100}],end=[{x:60,y:130},{x:260,y:130}];
  const pinched=C.pinch(pose,start,end),midWorld=C.unproject({x:150,y:100},pose),midAfter=C.project(midWorld,pinched);
  near(midAfter.x,160);near(midAfter.y,130);near(pinched.z,3);
});
