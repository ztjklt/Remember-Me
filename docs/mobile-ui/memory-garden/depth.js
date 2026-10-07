/* Three local views share the same seeded botanical geometry. No new data or model requests. */
(function(){
  const legacy=window.MemoryGarden,M=GardenDepthModel,G=GardenCamera;
  const {points,episodes,categories}=MemoryGardenData;let groups=M.build(points,episodes);
  const byId=new Map(points.map(p=>[p.id,p]));
  const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const count=g=>g.petals.reduce((n,p)=>n+p.ids.length,0);
  const category=p=>categories.find(c=>c.id===p.category);
  let route={level:'garden',group:null,petal:null},query='',filter='all',list=false,showFilters=false,pageIndex=0;
  // A copied deep link or refresh opens the same layer, after validating IDs locally.
  function routeFromHash(){let r={level:'garden',group:null,petal:null};try{const parts=location.hash.split('/').slice(1).map(decodeURIComponent);if(parts[0])r=M.move(r,{group:parts[0]},groups);if(parts[1])r=M.move(r,{petal:parts[1]},groups);}catch{/* malformed fragment: use the garden */}return r;}
  route=routeFromHash();
  const visits=new Map(),artCache=new Map();let abort,resizeObserver,flight,dragged=false,sceneIds=[],camera={x:0,y:0,z:1},sceneSequence=0,reuseScene=false;
  const key=r=>`${r.level}:${r.group||''}:${r.petal||''}`;
  function visit(r=route){if(!visits.has(key(r)))visits.set(key(r),{camera:defaultCamera(r),scroll:0});return visits.get(key(r));}
  const showList=()=>list||document.documentElement.classList.contains('large');
  const currentGroup=()=>groups.find(g=>g.id===route.group);
  const currentPetal=()=>currentGroup()?.petals.find(p=>p.id===route.petal);
  const match=p=>(filter==='all'||p.category===filter)&&[p.title,p.quote,episodes[p.episode].title,groups.find(g=>g.episode===p.episode)?.title,category(p).label].join(' ').includes(query.trim());
  const visibleGroups=()=>groups.filter(g=>g.petals.some(p=>p.ids.some(id=>match(byId.get(id)))));
  const positions=[{x:53,y:25,size:56},{x:25,y:60,size:51},{x:77,y:70,size:45}];
  const botanical=GardenBotanicalPose;
  function bloom(g,interactive=false){
    let i=0;
    if(!artCache.has(g.id))artCache.set(g.id,GardenArtwork.bloom({x:80,y:80,s:1,r:g.rotation,tilt:1,seed:g.seed},`depth-${g.id}`));
    let art=artCache.get(g.id);
    art=art.replaceAll('class="living-petal"',()=>{
      const petal=g.petals[i++];
      return `class="living-petal${petal.ids.length?'':' is-empty'}" ${interactive&&petal.ids.length?`data-depth-petal="${esc(petal.id)}"`:''}`;
    });
    return `<svg class="depth-bloom-art" data-flower-art="${esc(g.id)}" viewBox="0 0 160 160" aria-hidden="true">${art}</svg>`;
  }
  function stems(shown){return GardenArtwork.foliage(shown.map((g,i)=>{const p=positions[i],socket=botanical.socket(g.seed,g.rotation,p.size*3.6);return{id:g.id,seed:g.seed,x:p.x*3.6+socket.x,y:p.y*4.2+socket.y};}));}
  function controls(){return `<div class="depth-controls" aria-label="花园缩放"><span>拖动 · 双指缩放</span><button data-depth-action="out" aria-label="缩小花园">−</button><output id="depth-zoom">100%</output><button data-depth-action="in" aria-label="放大花园">＋</button><button data-depth-action="reset">归位</button></div>`;}
  function pageGroups(){
    const visible=visibleGroups(),pages=M.pages(visible);pageIndex=Math.max(0,Math.min(pageIndex,pages.length-1));
    if(route.level==='garden')sceneIds=(pages[pageIndex]||[]).map(g=>g.id);
    else if(!sceneIds.includes(route.group))sceneIds=(M.pages(groups).find(p=>p.some(g=>g.id===route.group))||[]).map(g=>g.id);
    return sceneIds.map(id=>groups.find(g=>g.id===id));
  }
  function placement(id){return positions[Math.max(0,sceneIds.indexOf(id))];}
  function flowerAnchor(id){const p=placement(id);return{x:p.x*3.6,y:p.y*4.2};}
  function defaultCamera(r){if(!r.group)return{x:0,y:0,z:1};const p=placement(r.group);return G.focus(flowerAnchor(r.group),.96/(p.size/100));}
  function scene(){
    if(reuseScene)return '<div id="depth-stage"></div>';
    const shown=pageGroups();
    return `<div class="depth-stage" id="depth-stage" tabindex="0" role="group" aria-label="记忆花园，拖动、双指或按钮缩放"><div class="depth-world" id="depth-world" data-scene-id="${++sceneSequence}">${stems(shown)}${shown.map((g,i)=>{const p=positions[i];return `<div class="depth-flower" data-bloom="${esc(g.id)}" style="left:${p.x}%;top:${p.y}%;width:${p.size}%">${bloom(g,true)}<button class="depth-flower-hit" data-depth-group="${esc(g.id)}" aria-label="走近${esc(g.title)}，${count(g)}个片段"><span class="depth-flower-label"><strong>${esc(g.title)}</strong><small>${episodes[g.episode].year} · ${count(g)} 个片段</small></span></button>${g.petals.map((p,i)=>{const pos=botanical.labels(g.seed,g.rotation)[i];return `<button class="depth-petal-label${(query||filter!=='all')&&p.ids.some(id=>match(byId.get(id)))?' is-match':''}" data-depth-petal="${esc(p.id)}" style="left:${pos.x}%;top:${pos.y}%;--point-color:${p.ids.length?category(byId.get(p.ids[0])).color:'#91a49b'}" ${p.ids.length?'':'disabled'} aria-label="${esc(p.title)}${p.ids.length?`，${p.ids.length}个片段`:''}"><i></i><span>${esc(p.title)}</span>${p.ids.length>1?`<small aria-hidden="true">${p.ids.length}</small>`:''}</button>`;}).join('')}</div>`;}).join('')}</div></div>`;
  }
  function listToggle(){return `<button data-depth-action="list" aria-pressed="${showList()}" ${document.documentElement.classList.contains('large')?'disabled':''}>${document.documentElement.classList.contains('large')?'大字号列表':showList()?'花园':'列表'}</button>`;}
  function overview(){
    const visible=visibleGroups(),pages=M.pages(visible);pageGroups();
    const filters=showFilters?`<div id="depth-filters" class="depth-filters" role="group" aria-label="按情感筛选"><button data-depth-filter="all" aria-pressed="${filter==='all'}">全部</button>${categories.map(c=>`<button data-depth-filter="${c.id}" aria-pressed="${filter===c.id}" style="--point-color:${c.color}"><i></i>${c.label}</button>`).join('')}</div>`:'';
    return `<div class="depth-hud"><div class="depth-tools"><button data-action="recordings">‹ 录音</button><span></span><button data-garden-act="search" aria-label="搜索记忆" aria-expanded="${Boolean(query)}">搜索</button><button data-depth-action="filters" aria-controls="depth-filters" aria-expanded="${showFilters}">${filter==='all'?'筛选':categories.find(c=>c.id===filter).label} ⌄</button>${listToggle()}</div><header class="depth-title"><span class="garden-eyebrow">A GARDEN OF MOMENTS</span><h1 tabindex="-1">把日子，慢慢种成花</h1><p>${visible.length} 朵花 · ${visible.flatMap(g=>g.petals.flatMap(p=>p.ids)).filter(id=>match(byId.get(id))).length} 个${filter!=='all'||query?'匹配的':''}记忆片段</p></header></div>${filters}${!visible.length?`<div class="garden-empty"><h3>还没有遇见这个词</h3><button data-depth-action="clear">清除搜索与筛选</button></div>`:showList()?`<div class="depth-group-list">${visible.map(g=>`<button data-depth-group="${esc(g.id)}">${bloom(g)}<span><strong>${esc(g.title)}</strong><small>${count(g)} 个片段 · ${episodes[g.episode].year}</small></span><span>↗</span></button>`).join('')}</div>`:`${scene()}${pages.length>1?`<nav class="depth-pagination" aria-label="更多回忆花丛"><button data-depth-action="prev" ${pageIndex===0?'disabled':''}>上一丛</button><span>${pageIndex+1} / ${pages.length}</span><button data-depth-action="next" ${pageIndex===pages.length-1?'disabled':''}>下一丛</button></nav>`:''}`}<p class="depth-caption">每一朵花里，都住着一段往事<br>轻触花朵，慢慢走近</p><div class="depth-floor">${showList()?'':controls()}${GardenAtmosphere.control()}</div>`;
  }
  function flower(){
    const g=currentGroup();pageGroups();
    return `<div class="depth-hud"><div class="depth-tools"><button data-depth-action="back" aria-label="返回花园">‹ 花园</button><span></span><small>花丛 / 一朵花</small>${listToggle()}</div><header class="depth-title"><span class="garden-eyebrow">${episodes[g.episode].year} · ${count(g)} 个记忆片段</span><h1 tabindex="-1">${esc(g.title)}</h1><p>${query||filter!=='all'?'亮起的花瓣，藏着你要找的回忆':'一片花瓣，一个值得停留的瞬间'}</p></header></div>${showList()?`<div class="depth-petal-list">${g.petals.filter(p=>p.ids.length).map(p=>`<button data-depth-petal="${esc(p.id)}"><span>${esc(p.title)}</span><small>${p.ids.length} 个片段 ↗</small></button>`).join('')}</div>`:`${scene()}`}<p class="depth-caption">轻触一片花瓣，让回忆缓缓展开</p><div class="depth-floor">${showList()?'':controls()}${GardenAtmosphere.control()}</div>`;
  }
  function petal(){
    const g=currentGroup(),p=currentPetal(),memory=byId.get(p.ids[0]);
    // Reuse the existing provenance, imagery choice, and real demo audio controls.
    const template=document.createElement('template');template.innerHTML=legacy.detail(memory.id);
    template.content.querySelectorAll('.reverie-toolbar,.related-memories,.reverie>.secondary,.reverie>.garden-eyebrow').forEach(el=>el.remove());
    const title=template.content.querySelector('.reverie-title');title.textContent=p.title;
    const lead=template.content.querySelector('.reverie-lead');lead.textContent=lead.textContent.replace(/。$/,'');
    const artActions=template.content.querySelector('.imagery-card-actions'),settings=document.createElement('details');
    settings.className='depth-art-settings';settings.innerHTML='<summary>意象与画风 <span>查看或调整</span></summary>';artActions.before(settings);settings.append(artActions);
    const reading=template.content.querySelector('.reverie-reading');
    for(const id of p.ids.slice(1)){
      const m=byId.get(id),section=document.createElement('section');section.className='depth-excerpt';
      section.innerHTML=`<h2>${esc(m.title)}</h2><blockquote>“${esc(m.quote)}”</blockquote><small>同一段演示原稿 · ${esc(category(m).label)}</small>`;
      reading.insertBefore(section,reading.querySelector('.reverie-editorial'));
    }
    template.content.querySelector('.audio-heading h2').textContent='让声音，把你带回去';
    const holder=document.createElement('div');holder.append(template.content);
    return `<div class="depth-top depth-reading-top"><button data-depth-action="back" aria-label="返回${esc(g.title)}">‹ ${esc(g.title)}</button><button data-depth-action="home">花园 ↗</button></div><div class="depth-reading"><div class="depth-paper" aria-hidden="true">${petalSVG()}</div><span class="depth-reading-kicker">${episodes[g.episode].year} · ${p.ids.length} 个片段 · 一片花瓣里的回忆</span>${holder.innerHTML}</div>`;
  }
  function petalSVG(){
    const g=currentGroup(),index=g.petals.findIndex(p=>p.id===route.petal),template=document.createElement('template');
    template.innerHTML=bloom(g);
    const petal=template.content.querySelectorAll('.living-petal')[index].cloneNode(true);
    petal.classList.add('paper-petal','botanical-v20');
    petal.querySelector('[clip-path]')?.removeAttribute('clip-path');
    const alpha=['.48','.30','0'];
    petal.querySelectorAll('radialGradient stop').forEach((stop,i)=>stop.setAttribute('stop-opacity',alpha[i]));
    // Keep the photographed petal's direction, folds and proportions. Only the
    // camera crop changes; lower petals no longer spin upright into a tall glyph.
    const {x:cx,y:cy}=botanical.focus(g.seed,index,g.rotation);
    return `<svg viewBox="${cx-48} ${cy-48} 96 96" preserveAspectRatio="xMidYMid meet" class="depth-paper-art"><g transform="rotate(${g.rotation})">${petal.outerHTML.replaceAll('v20-','paper-v20-')}</g></svg>`;
  }
  function render(q=''){if(q!==query&&route.level==='garden')visit().camera={x:0,y:0,z:1};query=q;return `<section class="memory-garden garden-depth" data-level="${route.level}" data-view="${showList()?'list':'art'}">${route.level==='garden'?overview():route.level==='flower'?flower():petal()}</section>`;}
  function paintCamera(world=document.getElementById('depth-world'),pose=camera){
    if(!world)return;
    const same=pose===camera;pose=GardenAtmosphere.constrain(pose);if(same)camera=pose;
    const {x,y,z}=pose;world.style.transform=`translate3d(${x/360*100}%,${y/420*100}%,0) scale(${z})`;
    GardenAtmosphere.paint(pose);
    world.style.setProperty('--camera-z',z);world.dataset.camera=JSON.stringify(pose);
    const output=document.getElementById('depth-zoom');if(output&&!flight)output.textContent=`${Math.round(z/defaultCamera(route).z*100)}%`;
    document.querySelector('[data-depth-action="out"]')?.toggleAttribute('disabled',z<=1);
    document.querySelector('[data-depth-action="in"]')?.toggleAttribute('disabled',z>=4.8);
  }
  function syncScene(stage=document.getElementById('depth-stage')){
    if(!stage)return;stage.dataset.level=route.level;
    stage.querySelectorAll('[data-sprig]').forEach(el=>{el.dataset.focused=String(el.dataset.sprig===route.group);});
    stage.querySelectorAll('[data-bloom]').forEach(el=>{
      const focused=el.dataset.bloom===route.group;el.dataset.focused=String(focused);
      const overview=route.level==='garden';el.querySelector('.depth-flower-hit').disabled=!overview;
      el.querySelectorAll('.depth-petal-label').forEach(b=>{b.inert=!focused||overview;});
    });
  }
  function mount({preserveCamera=false}={}){
    if(!preserveCamera)stopMotion(true);
    abort?.abort();resizeObserver?.disconnect();
    if(!document.querySelector('.garden-depth')){document.querySelector('.depth-search-clear')?.remove();legacy.mount();return;}
    mountSearch();
    document.getElementById('screen').scrollTop=visit().scroll;
    if(route.level==='petal'){
      legacy.mountDetail();
      return;
    }
    const stage=document.getElementById('depth-stage');if(!stage)return;
    GardenAtmosphere.measure(stage);
    if(!preserveCamera)camera={...visit().camera};syncScene(stage);paintCamera();abort=new AbortController();const signal=abort.signal,contacts=new Map();let start=[],origin;
    const pos=e=>{const b=stage.getBoundingClientRect();return{x:(e.clientX-b.left)*360/b.width,y:(e.clientY-b.top)*420/b.height};};
    const begin=()=>{start=[...contacts.values()];origin={...camera};};
    const surface=document.getElementById('screen'),isControl=e=>e.target.closest('button,input,select,a,summary')&&!e.target.closest('[data-depth-group],[data-depth-petal]');
    surface.addEventListener('pointerdown',e=>{if(e.button>0||isControl(e))return;stopMotion();if(!contacts.size)dragged=false;contacts.set(e.pointerId,pos(e));begin();},{signal});
    surface.addEventListener('pointermove',e=>{if(!contacts.has(e.pointerId))return;contacts.set(e.pointerId,pos(e));const now=[...contacts.values()];
      if(now.length>1){dragged=true;camera=G.pinch(origin,start.slice(0,2),now.slice(0,2));}
      else if(dragged||Math.hypot(now[0].x-start[0].x,now[0].y-start[0].y)>5){dragged=true;camera=G.constrain({...origin,x:origin.x+now[0].x-start[0].x,y:origin.y+now[0].y-start[0].y});}
      if(dragged){stage.classList.add('is-manipulating');surface.setPointerCapture(e.pointerId);camera=GardenAtmosphere.constrain(camera);visit().camera={...camera};paintCamera();}
    },{signal});
    const release=e=>{contacts.delete(e.pointerId);if(contacts.size)begin();else stage.classList.remove('is-manipulating');};
    window.addEventListener('pointerup',release,{signal});window.addEventListener('pointercancel',e=>{dragged=true;release(e);},{signal});surface.addEventListener('lostpointercapture',release,{signal});
    surface.addEventListener('wheel',e=>{if(isControl(e))return;e.preventDefault();stopMotion();camera=GardenAtmosphere.constrain(G.zoomAt(camera,camera.z*Math.exp(-e.deltaY*.002),pos(e)));visit().camera={...camera};paintCamera();},{passive:false,signal});
    stage.addEventListener('keydown',e=>{if(e.target!==stage)return;if(!['+','=','-','0','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;stopMotion();let c=camera;
      if(['+','=','-'].includes(e.key))c=G.zoomAt(c,c.z+(e.key==='-'?-.25:.25));
      else if(e.key==='0')c=defaultCamera(route);
      else if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))c=G.constrain({...c,x:c.x+(e.key==='ArrowLeft'?28:e.key==='ArrowRight'?-28:0),y:c.y+(e.key==='ArrowUp'?28:e.key==='ArrowDown'?-28:0)});
      else return;e.preventDefault();stopMotion();camera=c;visit().camera={...c};paintCamera();
    },{signal});
    resizeObserver=new ResizeObserver(()=>{GardenAtmosphere.measure(stage);paintCamera();});resizeObserver.observe(stage);
  }
  function stopMotion(keepPetal=false){if(!keepPetal)GardenPetalMotion.cancel();if(flight){const f=flight;flight=null;f.cancel();}document.querySelectorAll('.garden-depth').forEach(e=>e.getAnimations({subtree:true}).filter(a=>a.effect?.getTiming().iterations!==Infinity).forEach(a=>a.cancel()));}
  function teardown(){if(document.querySelector('#results>.garden-depth'))save();stopMotion();abort?.abort();resizeObserver?.disconnect();legacy.teardown();}
  function save(){visit().scroll=document.getElementById('screen').scrollTop;}
  function refresh(stage){
    legacy.teardown();abort?.abort();resizeObserver?.disconnect();
    const results=document.getElementById('results');reuseScene=!!stage;try{results.innerHTML=render(query);}finally{reuseScene=false;}
    if(stage)results.querySelector('#depth-stage')?.replaceWith(stage);
    mount({preserveCamera:!!stage});
  }
  function moveCamera(to,anchor,{world=document.getElementById('depth-world'),duration=G.duration,finish=()=>{},fade}={}){
    to=GardenAtmosphere.constrain(to);
    const from={...camera},interpolate=G.interpolate(from,to,anchor);
    if(!world||reducedMotion()){camera={...to};paintCamera(world);finish();return;}
    const stage=world.closest('.depth-stage');stage?.classList.add('is-travelling');paintCamera(world,from);
    // Precompute one world transform track. Browser compositor runs it, with no
    // per-frame layout, SVG path edits, backdrop blur, or inherited CSS variable writes.
    const poses=Array.from({length:91},(_,i)=>interpolate(i/90));
    const frames=poses.map((c,i)=>({offset:i/90,transform:`translate3d(${c.x/360*100}%,${c.y/420*100}%,0) scale(${c.z})`}));
    const animation=world.animate(frames,{duration,easing:'linear',fill:'both'});
    const sceneryAnimation=GardenAtmosphere.animate(poses,{duration,easing:'linear',fill:'both'}),start=document.timeline.currentTime;
    if(start!==null){animation.startTime=start;if(sceneryAnimation)sceneryAnimation.startTime=start;}
    const output=document.getElementById('depth-zoom');if(output)output.textContent=`${Math.round(to.z/defaultCamera(route).z*100)}%`;
    const fadeAnimation=fade?.animate([{opacity:1},{opacity:0,offset:.6},{opacity:0}],{duration,fill:'both'});
    const pose=()=>{const style=getComputedStyle(world),m=new DOMMatrixReadOnly(style.transform);return{x:m.m41/parseFloat(style.width)*360,y:m.m42/parseFloat(style.height)*420,z:m.a};};
    const diagnostics=new URLSearchParams(location.search).has('motion-check'),samples=[];let frame=0,done=false;
    function sample(){const c=pose();samples.push({time:Number(animation.currentTime||0),pose:c,focus:G.project(anchor,c)});frame=requestAnimationFrame(sample);}
    if(diagnostics)sample();
    const clean=()=>{cancelAnimationFrame(frame);stage?.classList.remove('is-travelling');animation.cancel();sceneryAnimation?.cancel();fadeAnimation?.cancel();if(flight?.world===world)flight=null;finish();};
    flight={world,cancel:()=>{if(done)return;done=true;camera=pose();paintCamera(world);clean();}};
    animation.finished.then(()=>{if(done)return;done=true;camera={...to};paintCamera(world);if(diagnostics){samples.push({time:duration,pose:to,focus:G.project(anchor,to)});world.dataset.motionReport=JSON.stringify(samples);}clean();},()=>{});
  }
  function transition(action,{history=true}={}){
    const next=M.move(route,action,groups);if(key(next)===key(route))return;
    const trail=window.history.state?.gardenTrail||[];
    if(history&&(action.back||action.home)){const parent=trail.map(key).lastIndexOf(key(next));if(parent>=0){window.history.go(parent-trail.length);return;}}
    const old={...route},enteringPetal=next.level==='petal',leavingPetal=old.level==='petal';
    const continued=(enteringPetal||leavingPetal)&&!reducedMotion()&&!showList()?GardenPetalMotion.hold():null;
    save();stopMotion(!!continued);const startCamera={...camera};legacy.pauseAudio();
    const stage=document.getElementById('depth-stage'),oldBounds=stage?.getBoundingClientRect();
    const anchor=flowerAnchor(next.group||old.group);
    const selected=enteringPetal?document.querySelector(`.living-petal[data-depth-petal="${CSS.escape(next.petal)}"]`):leavingPetal?document.querySelector('.paper-petal'):null;
    const handoff=continued||((enteringPetal||leavingPetal)&&!reducedMotion()&&!showList()?GardenPetalMotion.prepare(selected):null);
    const fallback=!handoff&&(!stage||enteringPetal||leavingPetal)&&!reducedMotion()?GardenPetalMotion.snapshot():null;
    const persisted=!enteringPetal&&!leavingPetal?stage:null;
    route=next;pageGroups();
    const destination={...visit().camera};
    if(persisted)visit().scroll=visit(old).scroll;
    refresh(persisted);camera=startCamera;
    const world=document.getElementById('results').querySelector('#depth-world');
    // Keep the viewport at its old on-screen position even when a search/filter panel closes.
    if(persisted&&oldBounds){const b=persisted.getBoundingClientRect();document.getElementById('screen').scrollTop+=b.top-oldBounds.top;}
    const focus=next.level==='garden'?document.querySelector(`button[data-depth-group="${CSS.escape(old.group)}"]`):next.level==='flower'&&old.petal?document.querySelector(`button[data-depth-petal="${CSS.escape(old.petal)}"]`):document.querySelector('.depth-title h1,.reverie-title');
    const restoreFocus=()=>{if(key(route)===key(next)&&focus?.isConnected)focus.focus({preventScroll:true});};
    if(enteringPetal){
      const target=document.querySelector('.paper-petal');
      if(handoff)GardenPetalMotion.run(handoff,target,{arriving:document.querySelector('#results>.garden-depth'),finish:restoreFocus});
      else if(fallback)GardenPetalMotion.dissolve(fallback,{finish:restoreFocus});
      else document.querySelector('.depth-reading')?.animate([{opacity:0},{opacity:1}],{duration:reducedMotion()?100:260,easing:'ease-out'});
    }else if(leavingPetal){
      camera={...destination};paintCamera(world);
      const target=document.querySelector(`.living-petal[data-depth-petal="${CSS.escape(old.petal)}"]`);
      if(handoff&&target)GardenPetalMotion.run(handoff,target,{reverse:true,arriving:document.querySelector('#results>.garden-depth'),finish:restoreFocus});
      else{handoff?.finish();if(fallback)GardenPetalMotion.dissolve(fallback,{finish:restoreFocus});else{document.querySelector('#results>.garden-depth')?.animate([{opacity:0},{opacity:1}],{duration:100,easing:'ease-out'});restoreFocus();}}
    }else if(fallback){
      camera={...destination};paintCamera(world);GardenPetalMotion.dissolve(fallback,{finish:restoreFocus});
    }else{
      paintCamera(world);moveCamera(destination,anchor,{world,finish:restoreFocus});
      document.querySelector('.depth-title')?.animate([{opacity:.15},{opacity:1}],{duration:reducedMotion()?100:280});
    }
    // Wait for an unfolding petal before moving focus into its reading controls.
    if(!handoff&&!fallback)focus?.focus({preventScroll:true});
    if(history){const method=action.back||action.home?'replaceState':'pushState';window.history[method]({gardenDepth:{...route},gardenTrail:method==='pushState'?[...trail,old]:[]},'',route.level==='garden'?'#archive':`#archive/${encodeURIComponent(route.group)}${route.petal?'/'+encodeURIComponent(route.petal):''}`);}
  }
  function mountSearch(){
    const box=document.getElementById('archive-search');if(!box)return;
    document.querySelector('.depth-tools [data-garden-act="search"]')?.setAttribute('aria-expanded',String(!box.classList.contains('hidden')));
    let clear=box.querySelector('.depth-search-clear');
    if(!clear){clear=document.createElement('button');clear.type='button';clear.className='depth-search-clear';clear.dataset.depthAction='clear-search';clear.setAttribute('aria-label','清空搜索');clear.innerHTML='<span aria-hidden="true">×</span>';box.append(clear);}
    clear.hidden=!query;
  }
  function clearSearch(){
    query='';search='';const input=document.getElementById('query');if(input)input.value='';
    if(route.level==='garden')visit().camera=defaultCamera(route);save();refresh();input?.focus({preventScroll:true});
  }
  function closeFilters(){
    showFilters=false;document.getElementById('depth-filters')?.remove();document.querySelector('[data-depth-action="filters"]')?.setAttribute('aria-expanded','false');
  }
  document.addEventListener('visibilitychange',()=>{
    document.documentElement.classList.toggle('app-background',document.hidden);
    if(document.hidden&&document.querySelector('.garden-depth')){stopMotion();if(route.level!=='petal'){camera={...visit().camera};paintCamera();}}
  });
  document.addEventListener('click',e=>{
    if(showFilters&&!e.target.closest('.depth-filters,[data-depth-action="filters"]'))closeFilters();
    const target=e.target.closest('[data-depth-group],[data-depth-petal],[data-depth-action],[data-depth-filter]');if(!target)return;
    e.stopImmediatePropagation();
    if(dragged&&target.closest('#depth-stage')&&e.detail!==0){dragged=false;return;}
    if(target.dataset.depthGroup){transition({group:target.dataset.depthGroup});return;}
    if(target.dataset.depthPetal){if(route.level==='garden'){transition({group:target.closest('[data-bloom]').dataset.bloom});}else transition({petal:target.dataset.depthPetal});return;}
    if(target.dataset.depthFilter){filter=target.dataset.depthFilter;pageIndex=0;showFilters=false;visit().camera=defaultCamera(route);save();refresh();document.querySelector('[data-depth-action="filters"]')?.focus({preventScroll:true});return;}
    const action=target.dataset.depthAction;
    if(action==='clear-search'){clearSearch();return;}
    if(action==='back'){transition({back:true});return;}if(action==='home'){transition({home:true});return;}
    if(action==='in'||action==='out'||action==='reset'){stopMotion();const target=action==='reset'?defaultCamera(route):G.zoomAt(camera,camera.z+(action==='in'?.25:-.25));visit().camera=target;moveCamera(target,G.unproject(G.center,camera),{duration:240});return;}
    stopMotion();
    const listSnapshot=action==='list'&&!reducedMotion()?GardenPetalMotion.snapshot():null;
    if(action==='list')list=!list;
    if(action==='filters'){showFilters=!showFilters;save();refresh(document.getElementById('depth-stage'));document.querySelector('[data-depth-action="filters"]')?.focus({preventScroll:true});return;}
    if(action==='clear'){filter='all';query='';search='';const q=document.getElementById('query');if(q)q.value='';}
    if(action==='prev'||action==='next'){pageIndex+=action==='next'?1:-1;visit().camera={x:0,y:0,z:1};}
    refresh();if(listSnapshot)GardenPetalMotion.dissolve(listSnapshot);document.querySelector(`[data-depth-action="${action}"]`)?.focus({preventScroll:true});
  },true);
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&showFilters){e.preventDefault();e.stopImmediatePropagation();closeFilters();document.querySelector('[data-depth-action="filters"]')?.focus({preventScroll:true});return;}if(e.key==='Escape'&&e.target.id==='query'){e.preventDefault();e.stopImmediatePropagation();if(query)clearSearch();else{document.getElementById('archive-search').classList.add('hidden');const toggle=document.querySelector('.depth-tools [data-garden-act="search"]');toggle?.setAttribute('aria-expanded','false');toggle?.focus({preventScroll:true});}return;}if(e.key==='Escape'&&route.level!=='garden'&&page==='archive'&&!document.querySelector('dialog[open]')){e.preventDefault();e.stopImmediatePropagation();transition({back:true});}},true);
  document.addEventListener('change',e=>{if(e.target.id==='reduce'){stopMotion();if(route.level!=='petal'){camera={...visit().camera};paintCamera();}}if(e.target.id==='large'&&document.querySelector('.garden-depth')){save();stopMotion();refresh();}});
  window.addEventListener('resize',()=>{stopMotion();if(route.level!=='petal'){camera={...visit().camera};paintCamera();}});
  window.addEventListener('popstate',e=>{
    if(page!=='archive')return;
    const r=e.state?.gardenDepth||routeFromHash();
    if(r.level==='garden')transition({home:true},{history:false});
    else if(r.level==='flower')transition({group:r.group},{history:false});
    else {if(route.group!==r.group||route.level!=='flower')transition({group:r.group},{history:false});transition({petal:r.petal},{history:false});}
  });
  function home(){
    if(page==='archive'&&mode==='memories'){transition({home:true});return true;}
    route={level:'garden',group:null,petal:null};camera={x:0,y:0,z:1};
    window.history.replaceState({gardenDepth:route},'','#archive');return false;
  }
  window.MemoryGarden={...legacy,render,mount,teardown,home};
})();
