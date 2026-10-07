const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const P=require('./botanical-v20-model.js'),M=require('./depth-model.js'),C=require('./camera.js'),motion=require('./petal-motion.js');
const {points,episodes}=require('./data.js'),groups=M.build(points,episodes);
const near=(a,b)=>assert.ok(Math.abs(a-b)<.001,`${a} differs from ${b}`);
const context={window:{GardenArtwork:{foliage:()=> 'preserved'},GardenBotanicalPose:P}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'botanical-v20.js'),'utf8'),context);
const A=context.window.GardenArtwork;

test('both oblique views have project-owned RGBA assets and five reachable memory petals',()=>{
  const used=new Set();
  for(const group of groups){
    const pose=P.pose(group.seed);used.add(pose.file);
    const png=fs.readFileSync(path.resolve(__dirname,'../../../assets/brand/forget-me-not/v20',pose.file));
    assert.equal(png.subarray(1,4).toString(),'PNG');assert.equal(png[25],6,'flower must retain alpha');
    const art=A.bloom({x:80,y:80,s:1,r:group.rotation,tilt:1,seed:group.seed},group.id);
    assert.equal((art.match(/class="living-petal"/g)||[]).length,5);
    assert.equal((art.match(/class="petal-photo"/g)||[]).length,5);
    for(const label of P.labels(group.seed,group.rotation)){assert.ok(label.x>4&&label.x<96&&label.y>4&&label.y<96);}
  }
  assert.equal(used.size,2);assert.equal(A.foliage(),'preserved');
});

test('image-space petal focus, clickable label and transition focus coincide after flower rotation',()=>{
  for(const group of groups){
    const art=A.bloom({x:80,y:80,s:1,r:group.rotation,tilt:1,seed:group.seed},group.id);
    const petals=[...art.matchAll(/data-petal-angle="([^"]+)" data-focal-x="([^"]+)" data-focal-y="([^"]+)"/g)];
    petals.forEach((match,i)=>{
      const focal=P.rotate({x:+match[2],y:+match[3]},+match[1]+group.rotation),focus=P.focus(group.seed,i,group.rotation),label=P.labels(group.seed,group.rotation)[i];
      near(focal.x,focus.x);near(focal.y,focus.y);near((label.x-50)*1.6,focus.x);near((label.y-50)*1.6,focus.y);
      const from={a:1,b:0,c:0,d:1,e:80,f:80},to={a:2.8,b:0,c:0,d:2.8,e:195-focus.x*2.8,f:220-focus.y*2.8},track=motion.track(from,to,focus);
      near(track(1).e,to.e);near(track(1).f,to.f);
      for(let t=0;t<=1;t+=.05){const m=track(t);assert.ok(m.a*m.d-m.b*m.c>0,'no flattening or flipped petal during zoom');}
    });
  }
  assert.equal(C.duration,620,'flower and petal transitions share the established duration');
});

test('stem endpoint stays on the photographed stalk as flowers rotate and scale',()=>{
  for(const pose of Object.values(P.poses))for(const angle of [-90,-12,8,15,90])for(const width of [120,160,201.6]){
    const seed=pose===P.poses.side?1:2,endpoint=P.socket(seed,angle,width),back=P.rotate(endpoint,-angle);
    near(back.x*160/width,pose.socket.x);near(back.y*160/width,pose.socket.y);
    assert.ok(Math.hypot(endpoint.x,endpoint.y)>10,'stalk must not incorrectly join the throat');
  }
});
