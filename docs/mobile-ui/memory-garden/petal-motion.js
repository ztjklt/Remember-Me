/* One photograph, two views. Approach its selected petal region with a
   non-singular camera matrix and retain the same texture at the handoff. */
(function(root){
  const camera=typeof module!=='undefined'&&module.exports?require('./camera.js'):root.GardenCamera;
  const project=(m,p)=>({x:m.a*p.x+m.c*p.y+m.e,y:m.b*p.x+m.d*p.y+m.f});
  function track(from,to,pivot){
    const pose=m=>({x:project(m,pivot).x,y:project(m,pivot).y,r:Math.atan2(m.b,m.a),sx:Math.hypot(m.a,m.b),sy:(m.a*m.d-m.b*m.c)/Math.hypot(m.a,m.b)});
    const a=pose(from),b=pose(to),turn=Math.atan2(Math.sin(b.r-a.r),Math.cos(b.r-a.r));
    return t=>{
      const {focus:p,zoom:u}=camera.timing(t),r=a.r+turn*u;
      const sx=Math.exp(Math.log(a.sx)*(1-u)+Math.log(b.sx)*u),sy=Math.exp(Math.log(a.sy)*(1-u)+Math.log(b.sy)*u);
      const m={a:Math.cos(r)*sx,b:Math.sin(r)*sx,c:-Math.sin(r)*sy,d:Math.cos(r)*sy};
      m.e=a.x+(b.x-a.x)*p-m.a*pivot.x-m.c*pivot.y;m.f=a.y+(b.y-a.y)*p-m.b*pivot.x-m.d*pivot.y;return m;
    };
  }
  const css=m=>`matrix(${m.a},${m.b},${m.c},${m.d},${m.e},${m.f})`;
  let sequence=0,active;
  function unique(node){
    const ids=new Map(),prefix=`journey-${++sequence}-`;
    node.querySelectorAll('[id]').forEach(el=>{ids.set(el.id,prefix+el.id);el.id=prefix+el.id;});
    node.querySelectorAll('*').forEach(el=>{for(const attr of [...el.attributes])if(attr.value.includes('url('))el.setAttribute(attr.name,attr.value.replace(/url\((['"]?)[^)#]*#([^)'"\s]+)\1\)/g,(all,q,id)=>ids.has(id)?`url(#${ids.get(id)})`:all));});
    return node;
  }
  function opacity(el){let n=el,value=1;while(n&&n!==document.body){value*=Number(getComputedStyle(n).opacity);n=n.parentElement;}return value;}
  function localMatrix(el,bounds){const m=el.getScreenCTM();return{a:m.a,b:m.b,c:m.c,d:m.d,e:m.e-bounds.left,f:m.f-bounds.top};}
  function art(el){
    const copy=unique(el.cloneNode(true));copy.removeAttribute('transform');copy.style.removeProperty('transform');copy.style.visibility='visible';copy.removeAttribute('data-depth-petal');
    // Approach the selected region of the complete photograph. Flying a cut
    // angular sector would expose artificial straight edges beside real folds.
    if(copy.querySelector('.petal-photo'))copy.querySelector('[clip-path]')?.removeAttribute('clip-path');
    return copy;
  }
  function cancel(){active?.finish();}
  function hold(){
    const j=active;if(!j||!j.cold||j.finished)return null;
    const matrix=new DOMMatrixReadOnly(getComputedStyle(j.moving).transform),layers=[...j.moving.children].map(el=>({el,opacity:getComputedStyle(el).opacity}));
    const shade=getComputedStyle(j.snapshot).opacity;
    if(j.target)j.target.style.visibility=j.visibility;
    j.animations.forEach(a=>a.cancel());j.animations=[];j.target=null;j.onfinish=null;
    const mixed=document.createElementNS('http://www.w3.org/2000/svg','g');
    layers.forEach(({el,opacity})=>{el.style.opacity=opacity;mixed.append(el);});
    j.moving.replaceChildren(mixed);j.cold=mixed;j.sourceOpacity=1;
    j.start={a:matrix.a,b:matrix.b,c:matrix.c,d:matrix.d,e:matrix.e,f:matrix.f};j.moving.style.transform=css(j.start);j.snapshot.style.opacity=shade;
    return j;
  }
  function prepare(source,{sceneOnly=false}={}){
    if(!source&&!sceneOnly)return null;
    cancel();
    const screen=document.getElementById('screen'),phone=document.querySelector('.phone'),bounds=screen.getBoundingClientRect(),p=phone.getBoundingClientRect();
    const surface=source?.querySelector('.living-petal-surface'),box=surface?.getBBox();
    const focal=source?.dataset.focalX!==undefined?{x:Number(source.dataset.focalX),y:Number(source.dataset.focalY)}:null;
    const start=source?localMatrix(source,bounds):null,cold=source?art(source):null,sourceOpacity=source?opacity(source):1;
    const overlay=document.createElement('div');overlay.className='petal-journey';overlay.inert=true;overlay.setAttribute('aria-hidden','true');
    Object.assign(overlay.style,{left:`${bounds.left}px`,top:`${bounds.top}px`,width:`${bounds.width}px`,height:`${bounds.height}px`});
    // The old phone keeps its own background, layout selectors, and scroll offset.
    // It is a short-lived visual snapshot; all IDs/paint references are isolated.
    const snapshot=unique(phone.cloneNode(true));snapshot.classList.add('petal-departure');
    Object.assign(snapshot.style,{position:'absolute',left:`${p.left-bounds.left}px`,top:`${p.top-bounds.top}px`,width:`${p.width}px`,height:`${p.height}px`,margin:'0',boxShadow:'none',transform:'none'});
    const ambientSelector='.cloud-bank,.firefly-flight,.firefly-glint',ambient=phone.querySelectorAll(ambientSelector);
    snapshot.querySelectorAll(ambientSelector).forEach((el,i)=>{const style=getComputedStyle(ambient[i]);el.style.transform=style.transform;el.style.opacity=style.opacity;el.style.animation='none';});
    snapshot.querySelectorAll('audio,video').forEach(el=>el.remove());
    if(source?.classList.contains('paper-petal'))snapshot.querySelector('.depth-paper')?.remove();
    else if(source){
      const selected=snapshot.querySelector(`.living-petal[data-depth-petal="${CSS.escape(source.dataset.depthPetal)}"]`);
      (source.querySelector('.petal-photo')?selected?.closest('.living-bloom'):selected)?.setAttribute('visibility','hidden');
    }
    overlay.append(snapshot);document.body.append(overlay);snapshot.querySelector('.screen').scrollTop=screen.scrollTop;
    const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg'),moving=document.createElementNS(ns,'g');
    svg.setAttribute('viewBox',`0 0 ${bounds.width} ${bounds.height}`);svg.classList.add('petal-flight-art','botanical-v17');
    if(source){moving.style.transformOrigin='0 0';moving.style.transform=css(start);cold.style.opacity=sourceOpacity;moving.append(cold);svg.append(moving);overlay.append(svg);}
    const journey={overlay,snapshot,svg,moving,cold,start,sourceOpacity,bounds,pivot:focal||(box?{x:box.x+box.width/2,y:box.y+box.height/2}:null),animations:[],target:null,finished:false,finish(){
      if(this.finished)return;this.finished=true;
      if(this.target)this.target.style.visibility=this.visibility;
      this.animations.forEach(a=>a.cancel());this.overlay.remove();if(active===this)active=null;this.onfinish?.();
    }};
    if(source)active=journey;return journey;
  }
  function dissolve(j,{duration=360,finish=()=>{}}={}){
    if(!j)return;active=j;j.onfinish=finish;
    const a=j.snapshot.animate([{opacity:1},{opacity:0}],{duration,easing:'cubic-bezier(.4,0,.2,1)',fill:'both'});
    j.animations.push(a);a.finished.then(()=>j.finish(),()=>{});
  }
  function run(journey,target,{reverse=false,arriving,finish=()=>{}}={}){
    if(!journey||!target){journey?.finish();finish();return;}
    const j=journey,to=localMatrix(target,j.bounds),warm=art(target),targetOpacity=opacity(target),interpolate=track(j.start,to,j.pivot),duration=camera.duration;
    j.target=target.querySelector('.petal-photo')?(target.closest('.living-bloom')||target):target;j.visibility=j.target.style.visibility;j.onfinish=finish;
    j.target.style.visibility='hidden';warm.style.opacity=0;j.moving.append(warm);
    const animate=(el,frames,options)=>{const a=el.animate(frames,{duration,fill:'both',...options});j.animations.push(a);return a;};
    const frames=Array.from({length:91},(_,i)=>({offset:i/90,transform:css(interpolate(i/90))}));
    const flight=animate(j.moving,frames,{easing:'linear'});
    animate(j.cold,[{opacity:j.sourceOpacity},{opacity:0,offset:.78},{opacity:0}],{});
    animate(warm,[{opacity:0},{opacity:targetOpacity,offset:.78},{opacity:targetOpacity}],{});
    animate(j.snapshot,[{opacity:Number(getComputedStyle(j.snapshot).opacity)},{opacity:0}],{duration:280,easing:'cubic-bezier(.2,0,.2,1)'});
    // Text appears as the macro texture opens, without a separate waiting phase.
    if(arriving)animate(arriving,[{opacity:0},{opacity:1,offset:.64},{opacity:1}],{});
    const diagnostics=new URLSearchParams(location.search).has('motion-check');let raf;
    const report={duration,source:j.start,target:to,petalPathSame:j.cold.querySelector('.living-petal-surface').getAttribute('d')===warm.querySelector('.living-petal-surface').getAttribute('d'),photoSame:j.cold.querySelector('image')?.getAttribute('href')===warm.querySelector('image')?.getAttribute('href'),samples:[]};
    if(diagnostics){const sample=()=>{const m=new DOMMatrixReadOnly(getComputedStyle(j.moving).transform);report.samples.push({time:Number(flight.currentTime||0),matrix:{a:m.a,b:m.b,c:m.c,d:m.d,e:m.e,f:m.f},cold:getComputedStyle(j.cold).opacity,warm:getComputedStyle(warm).opacity});raf=requestAnimationFrame(sample);};sample();}
    const finishFlight=()=>{cancelAnimationFrame(raf);if(diagnostics){const m=new DOMMatrixReadOnly(getComputedStyle(j.moving).transform);report.endMatrix={a:m.a,b:m.b,c:m.c,d:m.d,e:m.e,f:m.f};report.liveTarget=localMatrix(target,j.bounds);document.getElementById('results').dataset.petalMotionReport=JSON.stringify(report);}j.finish();};
    flight.finished.then(finishFlight,()=>{cancelAnimationFrame(raf);});
  }
  const api={track,prepare,run,cancel,hold,snapshot:()=>prepare(null,{sceneOnly:true}),dissolve};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.GardenPetalMotion=api;
})(typeof window==='undefined'?{}:window);
