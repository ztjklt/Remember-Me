/* A persistent, non-interactive layer behind the garden. Tiny distant glints
   move and flash independently; nothing in this layer represents a memory. */
(function(){
  const scenes=['pond','path','woodland'],storage='remember-me-garden-v20';
  const phone=document.querySelector('.phone'),scenery=phone.querySelector('.scenery'),select=document.getElementById('garden-scene');
  let saved={};try{saved=JSON.parse(localStorage.getItem(storage)||'{}');}catch{}
  if(!saved||typeof saved!=='object')saved={};
  let chosen=new URLSearchParams(location.search).get('garden');if(!scenes.includes(chosen))chosen=scenes.includes(saved.scene)?saved.scene:'pond';
  let paused=!!saved.paused,generation=0,current=null,frame=0,bounds=null;
  const layer=document.createElement('div');layer.className='garden-atmosphere';layer.setAttribute('aria-hidden','true');layer.inert=true;
  layer.innerHTML='<div class="garden-distance"></div><div class="garden-mist"></div><div class="garden-fireflies"></div>';scenery.append(layer);
  const distance=layer.querySelector('.garden-distance'),fireflies=layer.querySelector('.garden-fireflies');
  // x/y in percent: dispersed shadowed margins, never a decorative ring.
  const points=[[8,48,1.1,8.7,-2.05],[88,42,.9,7.1,-4.8],[17,70,1.35,9.6,-6.3],[79,66,1.1,6.7,-1.45],[6,83,1.55,10.3,-3.1],[92,77,1.25,8.1,-6.7],[27,85,.85,7.6,-1.8],[71,87,1.05,9.3,-5.6],[82,55,.8,11.2,-2.55]];
  fireflies.innerHTML=points.map(([x,y,size,period,delay],i)=>`<span class="firefly-flight" style="left:${x}%;top:${y}%;--flight:${17+i*2.1}s;--drift-x:${i%2?9:-7}px;--drift-y:${-6-i%4*2}px;--phase:${-i*3.3}s"><i class="firefly-glint${i%3===1?' firefly-pair':''}" style="--glint-size:${size}px;--pulse:${period}s;--pulse-phase:${delay}s"></i></span>`).join('');
  const reduced=()=>document.documentElement.classList.contains('reduce')||matchMedia('(prefers-reduced-motion:reduce)').matches;
  function persist(){try{localStorage.setItem(storage,JSON.stringify({scene:chosen,paused}));}catch{}}
  function sync(){
    phone.classList.toggle('garden-still',paused);phone.dataset.gardenScene=chosen;
    document.querySelectorAll('[data-garden-ambient]').forEach(b=>{b.textContent=reduced()?'微光已静止':paused?'让微光流动':'暂停微光';b.setAttribute('aria-pressed',String(paused));b.disabled=reduced();});
  }
  async function choose(id,{save=true}={}){
    if(!scenes.includes(id))return;
    const token=++generation,status=document.getElementById('garden-scene-status'),image=new Image();
    if(status)status.textContent='正在布置花园';
    image.className='garden-place';image.alt='';image.width=1024;image.height=1536;image.decoding='async';image.src=`nature/garden-v20/${id}.png`;
    try{await image.decode();}catch{if(token===generation){if(status)status.textContent='背景未加载，可以重新选择';if(select)select.value=chosen;}return;}
    if(token!==generation)return;
    const old=current;current=image;distance.append(image);chosen=id;if(select)select.value=id;sync();if(save)persist();
    layer.dataset.ready=id;if(status)status.textContent='仅设计预览，可随时切换';
    if(old){if(reduced())old.remove();else{const a=old.animate([{opacity:1},{opacity:0}],{duration:280,fill:'forwards'});old.style.zIndex='1';a.finished.then(()=>old.remove(),()=>old.remove());}}
  }
  function resetParallax(){cancelAnimationFrame(frame);frame=0;layer.style.setProperty('--garden-x','0px');layer.style.setProperty('--garden-y','0px');}
  phone.addEventListener('pointerenter',()=>{bounds=phone.getBoundingClientRect();});
  phone.addEventListener('pointermove',e=>{
    if(e.pointerType!=='mouse'||e.buttons||paused||reduced()||!phone.querySelector('.garden-depth'))return;
    if(!bounds)bounds=phone.getBoundingClientRect();const x=(e.clientX-bounds.left)/bounds.width-.5,y=(e.clientY-bounds.top)/bounds.height-.5;
    cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{layer.style.setProperty('--garden-x',`${Math.max(-3,Math.min(3,-x*6))}px`);layer.style.setProperty('--garden-y',`${Math.max(-2,Math.min(2,-y*4))}px`);frame=0;});
  });
  phone.addEventListener('pointerleave',resetParallax);phone.addEventListener('pointerdown',resetParallax);window.addEventListener('resize',()=>{bounds=null;resetParallax();});
  document.addEventListener('visibilitychange',()=>{document.documentElement.classList.toggle('app-background',document.hidden);if(document.hidden)resetParallax();});
  document.addEventListener('click',e=>{if(!e.target.closest('[data-garden-ambient]'))return;paused=!paused;persist();sync();if(paused)resetParallax();});
  document.addEventListener('change',e=>{if(e.target.id==='garden-scene')choose(e.target.value);if(e.target.id==='reduce'){sync();resetParallax();}});
  matchMedia('(prefers-reduced-motion:reduce)').addEventListener('change',()=>{sync();resetParallax();});
  rootApi();
  function rootApi(){window.GardenAtmosphere={control:()=>`<button class="garden-ambient-toggle" data-garden-ambient aria-pressed="${paused}" ${reduced()?'disabled':''}>${reduced()?'微光已静止':paused?'让微光流动':'暂停微光'}</button>`,sync};}
  sync();choose(chosen,{save:false});
})();
