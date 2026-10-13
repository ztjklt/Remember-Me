/* Persistent scenic plane. Only entry to the garden chooses a new random scene;
   flower/petal navigation retains the same place and camera. */
(function(){
  const M=GardenSceneModel,storage='remember-me-garden-v21',phone=document.querySelector('.phone'),scenery=phone.querySelector('.scenery'),select=document.getElementById('garden-scene');
  let saved={};try{saved=JSON.parse(localStorage.getItem(storage)||'{}');}catch{}if(!saved||typeof saved!=='object')saved={};
  const valid=id=>M.scenes.some(s=>s.id===id),query=new URLSearchParams(location.search).get('garden');
  let mode=valid(query)?query:valid(saved.mode)?saved.mode:'auto',chosen=valid(saved.last)?saved.last:null,paused=!!saved.paused,active=false,generation=0,current=null,frame=0,bounds=null,geometry=null;
  const layer=document.createElement('div');layer.className='garden-atmosphere';layer.setAttribute('aria-hidden','true');layer.inert=true;
  layer.innerHTML='<div class="garden-camera"><div class="garden-distance"></div><div class="garden-fireflies"></div></div><div class="garden-mist"></div>';scenery.append(layer);
  const camera=layer.querySelector('.garden-camera'),distance=layer.querySelector('.garden-distance'),fireflies=layer.querySelector('.garden-fireflies');
  const points=[[8,48,1.1,8.7,-2.05],[88,42,.9,7.1,-4.8],[17,70,1.35,9.6,-6.3],[79,66,1.1,6.7,-1.45],[6,83,1.55,10.3,-3.1],[92,77,1.25,8.1,-6.7],[27,85,.85,7.6,-1.8],[71,87,1.05,9.3,-5.6],[82,55,.8,11.2,-2.55]];
  fireflies.innerHTML=points.map(([x,y,size,period,delay],i)=>`<span class="firefly-flight" style="left:${x}%;top:${y}%;--flight:${17+i*2.1}s;--drift-x:${i%2?9:-7}px;--drift-y:${-6-i%4*2}px;--phase:${-i*3.3}s"><i class="firefly-glint${i%3===1?' firefly-pair':''}" style="--glint-size:${size}px;--pulse:${period}s;--pulse-phase:${delay}s"></i></span>`).join('');
  const reduced=()=>document.documentElement.classList.contains('reduce')||matchMedia('(prefers-reduced-motion:reduce)').matches;
  function persist(){try{localStorage.setItem(storage,JSON.stringify({mode,last:chosen,paused}));}catch{}}
  function sync(){
    phone.classList.toggle('garden-still',paused);phone.classList.toggle('garden-night',chosen==='night');phone.dataset.gardenScene=chosen||'';
    if(select)select.value=mode;
    document.querySelectorAll('[data-garden-ambient]').forEach(b=>{b.textContent=reduced()?'微光已静止':paused?'让微光流动':'暂停微光';b.setAttribute('aria-pressed',String(paused));b.disabled=reduced();});
    document.querySelectorAll('[data-garden-next]').forEach(b=>{b.textContent=`${M.scenes.find(s=>s.id===chosen)?.name||'花园光景'} ↻`;b.setAttribute('aria-label','换一处花园');});
  }
  async function choose(id){
    const scene=M.scenes.find(s=>s.id===id);if(!scene)return;
    const token=++generation,status=document.getElementById('garden-scene-status'),image=new Image();if(status)status.textContent='正在布置花园';
    image.className='garden-place';image.alt='';image.width=1024;image.height=1536;image.decoding='async';image.src=scene.src;
    try{await image.decode();}catch{if(token===generation){if(status)status.textContent='背景未加载，保留当前光景';}return;}
    if(token!==generation)return;
    distance.getAnimations({subtree:true}).forEach(a=>a.cancel());distance.querySelectorAll('img').forEach(i=>{if(i!==current)i.remove();});
    const old=current;current=image;distance.append(image);chosen=id;sync();persist();layer.dataset.ready=id;
    if(status)status.textContent=mode==='auto'?'重新进入花园时轮换，同一段回忆保持同一光景':'已固定这处光景';
    if(old){if(reduced())old.remove();else{old.style.zIndex='1';const a=old.animate([{opacity:1},{opacity:0}],{duration:420,fill:'forwards'});a.finished.then(()=>old.remove(),()=>{if(old!==current)old.remove();});}}
  }
  function resetParallax(){cancelAnimationFrame(frame);frame=0;layer.style.setProperty('--garden-x','0px');layer.style.setProperty('--garden-y','0px');}
  phone.addEventListener('pointerenter',()=>{bounds=phone.getBoundingClientRect();});
  phone.addEventListener('pointermove',e=>{if(e.pointerType!=='mouse'||e.buttons||paused||reduced()||!active)return;if(!bounds)bounds=phone.getBoundingClientRect();const x=(e.clientX-bounds.left)/bounds.width-.5,y=(e.clientY-bounds.top)/bounds.height-.5;cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{layer.style.setProperty('--garden-x',`${Math.max(-3,Math.min(3,-x*6))}px`);layer.style.setProperty('--garden-y',`${Math.max(-2,Math.min(2,-y*4))}px`);frame=0;});});
  phone.addEventListener('pointerleave',resetParallax);phone.addEventListener('pointerdown',resetParallax);window.addEventListener('resize',()=>{bounds=null;resetParallax();});
  document.addEventListener('visibilitychange',()=>{document.documentElement.classList.toggle('app-background',document.hidden);if(document.hidden)resetParallax();});
  document.addEventListener('click',e=>{if(e.target.closest('[data-garden-next]')){mode='auto';choose(M.next(chosen));return;}if(!e.target.closest('[data-garden-ambient]'))return;paused=!paused;persist();sync();if(paused)resetParallax();});
  document.addEventListener('change',e=>{if(e.target.id==='garden-scene'){mode=valid(e.target.value)?e.target.value:'auto';choose(mode==='auto'?M.next(chosen):mode);}if(e.target.id==='reduce'){sync();resetParallax();}});
  matchMedia('(prefers-reduced-motion:reduce)').addEventListener('change',()=>{sync();resetParallax();});
  function updateEntry(){const now=!!phone.querySelector('.garden-depth');if(now===active)return;active=now;if(now)choose(mode==='auto'?M.next(chosen):mode);sync();}
  new MutationObserver(updateEntry).observe(document.getElementById('screen'),{childList:true,subtree:true});
  window.GardenAtmosphere={
    control:()=>`<div class="garden-scene-actions"><button data-garden-next aria-label="换一处花园">${M.scenes.find(s=>s.id===chosen)?.name||'花园光景'} ↻</button><button class="garden-ambient-toggle" data-garden-ambient aria-pressed="${paused}" ${reduced()?'disabled':''}>${reduced()?'微光已静止':paused?'让微光流动':'暂停微光'}</button></div>`,sync,
    measure(stage){geometry=M.metrics(stage.getBoundingClientRect(),scenery.getBoundingClientRect());camera.style.transformOrigin=`${geometry.ox}px ${geometry.oy}px`;camera.dataset.geometry=JSON.stringify(geometry);},
    constrain:c=>M.constrain(c,geometry),
    paint(c){if(geometry){camera.style.transform=M.css(c,geometry);camera.dataset.camera=JSON.stringify(c);}},
    animate(poses,options){return geometry?camera.animate(poses.map((c,i)=>({offset:i/(poses.length-1),transform:M.css(c,geometry)})),options):null;}
  };
  updateEntry();
})();
