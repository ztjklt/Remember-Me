/* Local interactive study. No microphone, model calls or analytics. Image selections persist locally in imagery.js. */
window.MemoryGarden=(()=>{
  const {categories,episodes,points}=MemoryGardenData,G=GardenGeometry;
  const state={camera:{z:1,x:0,y:0},filter:'all',selected:null,view:'flower',layout:'flower',query:'',focusReturn:false,filtersOpen:false,branch:0};
  const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const category=id=>categories.find(c=>c.id===id),find=id=>points.find(p=>p.id===id);
  const photo=p=>`memory-garden/images/${episodes[p.episode].image}.png`;
  const matches=p=>(state.filter==='all'||p.category===state.filter)&&[p.title,p.quote,episodes[p.episode].title,category(p.category).label].join(' ').includes(state.query.trim());
  const clock=n=>`${Math.floor(n/60).toString().padStart(2,'0')}:${Math.floor(n%60).toString().padStart(2,'0')}`;
  let stageAbort,observer,dragged=false,playEpoch=0,audioMessage='轻触播放，听完整故事';
  const audio=document.createElement('audio');audio.id='garden-audio';audio.preload='metadata';audio.hidden=true;document.body.append(audio);
  function flower(displayed){
    const artwork=GardenArtwork.render(state.layout);
    // A minimum spanning tree within each source story keeps links legible, without inventing relationships.
    const edges=G.storyEdges(displayed,state.layout).map(({a,b,episode})=>{
      const cx=(a.x+b.x)/2-(b.y-a.y)*.09,cy=(a.y+b.y)/2+(b.x-a.x)*.09;
      return `<path data-story="${episode}" d="M${a.x} ${a.y} Q${cx} ${cy} ${b.x} ${b.y}"/>`;
    });
    return `<div class="garden-stage" id="garden-stage" data-layout="${state.layout}" tabindex="0" role="group" aria-label="记忆${state.layout==='flower'?'花枝':'星丛'}，拖动平移，双指缩放，也可使用下方按钮或方向键及加减键"><div class="garden-world" id="garden-world"><svg class="garden-drawing" viewBox="0 0 360 400" aria-hidden="true" focusable="false">${artwork}<g class="garden-edges">${edges.join('')}</g></svg>${displayed.map(p=>{const xy=G.point(p.layoutIndex,state.layout),c=category(p.category);return `<button class="memory-star" data-memory="${p.id}" data-story="${p.episode}" style="left:${xy.x/360*100}%;top:${xy.y/400*100}%;--point-color:${c.color}" aria-label="${esc(p.title)} · ${c.label}" aria-expanded="${state.selected===p.id}" aria-controls="garden-bubble" ${matches(p)?'':'hidden'}><span class="star-halo"></span><span class="star-core"></span><span class="star-title">${esc(p.title)}</span></button>`;}).join('')}</div><div class="garden-bubble-host" id="garden-bubble"></div><span class="garden-watermark" aria-hidden="true">${state.layout==='flower'?'把经过的日子，开成一枝花':'散落的时光，也有自己的星轨'}</span></div>`;
  }
  function render(query=''){
    state.query=query;
    const visible=points.filter(matches),branches=G.branches(points,matches);
    state.branch=Math.max(0,Math.min(state.branch,branches.length-1));
    const current=branches[state.branch];
    const legend=`<div class="garden-filter-panel" id="garden-filters" ${state.filtersOpen?'':'hidden'}><div class="garden-legend" aria-label="按记忆标签筛选"><button data-filter="all" aria-pressed="${state.filter==='all'}">全部</button>${categories.map(c=>`<button data-filter="${c.id}" style="--point-color:${c.color}" aria-pressed="${state.filter===c.id}"><i aria-hidden="true"></i>${c.label}</button>`).join('')}</div><p class="garden-filter-note">颜色代表记忆主题 · 花瓣纹理为装饰<br>亮点对应记忆，点亮可看同一故事的连线</p></div>`;
    return `<div class="memory-garden"><div class="garden-toolbar">${state.view==='flower'?`<div class="garden-formats" role="group" aria-label="记忆图样式"><button data-garden-layout="flower" aria-pressed="${state.layout==='flower'}">花枝</button><button data-garden-layout="constellation" aria-pressed="${state.layout==='constellation'}">星丛</button></div>`:'<span class="garden-eyebrow">那些小小的瞬间</span>'}<button class="garden-filter" data-garden-act="filters" aria-expanded="${state.filtersOpen}" aria-controls="garden-filters">${state.filter==='all'?'筛选':category(state.filter).label} ⌄</button><button class="garden-view" data-garden-act="view" aria-label="${state.view==='flower'?'切换为记忆列表':'切换为记忆花图'}">${state.view==='flower'?'列表':'花图'}</button></div>${legend}<div class="garden-section-head"><p class="garden-count" role="status">${visible.length} 个记忆点 · ${new Set(visible.map(p=>p.episode)).size} 段示例故事</p><span>${state.view==='flower'?'轻触亮点，走近往事':''}</span></div>${visible.length?(state.view==='flower'?flower(current.points):`<div class="garden-list">${visible.map(p=>`<button data-memory="${p.id}" class="garden-list-item"><img src="${photo(p)}" alt="" width="72" height="48"><span><strong>${p.title}</strong><small>${category(p.category).label} · ${episodes[p.episode].year}</small></span><span aria-hidden="true">↗</span></button>`).join('')}</div><div id="garden-bubble" class="list-bubble"></div>`):'<div class="garden-empty"><h3>还没有遇见这个词</h3><p>试试“汤”“小雨”或“灯”，也可以清除筛选</p><button class="secondary" data-garden-act="clear">清除搜索与筛选</button></div>'}${visible.length&&state.view==='flower'?`<div class="garden-controls" aria-label="花图缩放"><span>拖动 · 双指缩放</span><button data-garden-act="out" aria-label="缩小花图">−</button><output id="garden-zoom" aria-label="缩放比例">100%</output><button data-garden-act="in" aria-label="放大花图">＋</button><button data-garden-act="reset">归位</button></div>${branches.length>1?`<nav class="garden-branch-nav" aria-label="浏览更多花枝"><button data-garden-act="previous-branch" ${state.branch===0?'disabled':''}>← 上一枝</button><span>第 ${state.branch+1} / ${branches.length} 枝</span><button data-garden-act="next-branch" ${state.branch===branches.length-1?'disabled':''}>下一枝 →</button></nav>`:''}`:''}<p class="garden-footnote">把经过的日子，开成一枝花</p></div>`;
  }
  function paintCamera(){
    const world=document.getElementById('garden-world');if(!world)return;
    const {x,y,z}=state.camera;
    world.style.transform=`translate(${x/360*100}%,${y/400*100}%) scale(${z})`;
    world.style.setProperty('--inverse-zoom',1/z);
    const output=document.getElementById('garden-zoom');if(output)output.textContent=`${Math.round(z*100)}%`;
    document.querySelector('[data-garden-act="out"]')?.toggleAttribute('disabled',z<=1);
    document.querySelector('[data-garden-act="in"]')?.toggleAttribute('disabled',z>=2.8);
  }
  function closeBubble(restore=false){
    const id=state.selected;state.selected=null;
    const host=document.getElementById('garden-bubble');if(host)host.innerHTML='';
    document.querySelectorAll('.memory-star').forEach(b=>b.setAttribute('aria-expanded','false'));
    highlightStory(null);
    if(restore)document.querySelector(`[data-memory="${id}"]`)?.focus({preventScroll:true});
  }
  function bubble(id,focus=true){
    const p=find(id);if(!p)return;state.selected=id;
    const host=document.getElementById('garden-bubble');if(!host)return;
    const ep=episodes[p.episode],c=category(p.category);
    const stage=document.getElementById('garden-stage'),node=document.querySelector(`[data-memory="${id}"]`);
    const stageBox=stage?.getBoundingClientRect(),nodeBox=node?.getBoundingClientRect();
    host.classList.toggle('bubble-top',Boolean(stageBox&&nodeBox&&nodeBox.top+24>stageBox.top+stageBox.height/2));
    host.innerHTML=`<article class="memory-bubble" aria-label="记忆预览"><button class="bubble-close" data-garden-act="close" aria-label="关闭记忆预览">×</button><div class="bubble-topline"><img src="${photo(p)}" alt="" width="72" height="48"><div><small>${c.label} · ${ep.year}</small><h3 tabindex="-1">${p.title}</h3></div></div><p>“${p.quote}”</p><p class="bubble-story">${ep.title} · ${points.filter(q=>q.episode===p.episode).length} 颗同源记忆</p><button class="bubble-enter" data-garden-act="enter">走进这段回忆 <span aria-hidden="true">↗</span></button></article>`;
    document.querySelectorAll('.memory-star').forEach(b=>b.setAttribute('aria-expanded',String(b.dataset.memory===id)));
    highlightStory(p.episode);
    if(stageBox&&nodeBox){const hb=host.getBoundingClientRect();host.style.setProperty('--bubble-tail',`${Math.max(22,Math.min(hb.width-22,nodeBox.left+24-hb.left))}px`);}
    if(focus){host.querySelector('h3').focus({preventScroll:true});host.scrollIntoView({block:'nearest',behavior:'auto'});}
  }
  function highlightStory(episode){
    const stage=document.getElementById('garden-stage');if(!stage)return;
    stage.classList.toggle('has-selection',Boolean(episode));
    stage.querySelectorAll('[data-story]').forEach(el=>el.classList.toggle('is-related',Boolean(episode&&el.dataset.story===episode)));
  }
  function mount(){
    stageAbort?.abort();observer?.disconnect();
    if(page==='reverie'){mountAudio();return;}
    const stage=document.getElementById('garden-stage');
    if(stage)paintCamera();
    if(state.selected&&find(state.selected)&&matches(find(state.selected)))bubble(state.selected,false);else closeBubble();
    if(!stage)return;
    paintCamera();stageAbort=new AbortController();const signal=stageAbort.signal,contacts=new Map();let start=[],origin=state.camera;
    const position=e=>{const b=stage.getBoundingClientRect();return {x:(e.clientX-b.left)*360/b.width,y:(e.clientY-b.top)*400/b.height};};
    const begin=()=>{start=[...contacts.values()].map(p=>({...p}));origin={...state.camera};};
    stage.addEventListener('pointerdown',e=>{if(e.target.closest('.memory-bubble')||e.button>0)return;if(contacts.size===0)dragged=false;contacts.set(e.pointerId,position(e));(e.target.closest('.memory-star')||stage).setPointerCapture(e.pointerId);begin();},{signal});
    stage.addEventListener('pointermove',e=>{
      if(!contacts.has(e.pointerId))return;contacts.set(e.pointerId,position(e));const now=[...contacts.values()];
      const delta=Math.hypot(now[0].x-start[0].x,now[0].y-start[0].y);
      if(now.length>=2){dragged=true;state.camera=G.pinch(origin,start.slice(0,2),now.slice(0,2));}
      else if(delta>5||dragged){dragged=true;state.camera=G.constrain({...origin,x:origin.x+now[0].x-start[0].x,y:origin.y+now[0].y-start[0].y});}
      if(dragged){closeBubble();paintCamera();}
    },{signal});
    const release=e=>{contacts.delete(e.pointerId);if(contacts.size)begin();};
    stage.addEventListener('pointerup',release,{signal});stage.addEventListener('pointercancel',e=>{dragged=true;release(e);},{signal});
    stage.addEventListener('lostpointercapture',release,{signal});
    stage.addEventListener('wheel',e=>{e.preventDefault();closeBubble();state.camera=G.zoomAt(state.camera,state.camera.z*Math.exp(-e.deltaY*.002),position(e));paintCamera();},{signal,passive:false});
    stage.addEventListener('keydown',e=>{
      if(!['+','=','-','0','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)||e.target!==stage)return;e.preventDefault();closeBubble();
      if(e.key==='0')state.camera={z:1,x:0,y:0};else if(['+','=','-'].includes(e.key))state.camera=G.zoomAt(state.camera,state.camera.z+(e.key==='-'?-.25:.25));
      else state.camera=G.constrain({...state.camera,x:state.camera.x+(e.key==='ArrowLeft'?28:e.key==='ArrowRight'?-28:0),y:state.camera.y+(e.key==='ArrowUp'?28:e.key==='ArrowDown'?-28:0)});
      paintCamera();
    },{signal});
    observer=new ResizeObserver(paintCamera);observer.observe(stage);
    if(state.focusReturn){state.focusReturn=false;document.querySelector(`[data-memory="${state.selected}"]`)?.focus({preventScroll:true});}
  }
  function scene(){
    const p=find(state.selected)||points[0],ep=episodes[p.episode],c=category(p.category);
    state.selected=p.id;
    const related=points.filter(q=>q.episode===p.episode&&q.id!==p.id).slice(0,3);
    return `<div class="reverie"><div class="reverie-toolbar"><button data-garden-act="back" aria-label="返回记忆花图">← <span>记忆花园</span></button><span class="small">${ep.year} · 林岚的示例故事</span></div><span class="garden-eyebrow">A LITTLE MOMENT, REMEMBERED</span><h1 class="reverie-title" tabindex="-1">${p.title}</h1><p class="reverie-lead">${p.reflection}</p><div class="reverie-layout"><div class="reverie-reading"><span class="memory-tag" style="--point-color:${c.color}">${c.label} · ${c.meaning}</span><h2>当时说过的话</h2><blockquote>“${p.quote}”</blockquote><p class="small">演示原稿摘录 · 来自《${ep.title}》</p><div class="reverie-editorial"><p>标题与导语为演示整理文案。这里的摘录保留原稿措辞；时间指故事发生年份。</p><a href="memory-garden/sources/${p.episode}.txt" target="_blank" rel="noopener">阅读完整演示原稿 ↗</a></div></div><aside class="reverie-media" aria-label="意象与声音">${MemoryImagery.render(p)}<div class="garden-audio"><div class="audio-heading"><div><span class="garden-eyebrow">LISTEN AGAIN</span><h2>让声音，把你带回去。</h2></div><button id="garden-play" class="garden-play" data-garden-act="play" aria-label="播放整段合成示例">▶</button></div><input id="garden-seek" type="range" min="0" max="${ep.duration}" step=".1" value="0" aria-label="合成示例音频进度" disabled><div class="garden-audio-times"><span id="garden-current">00:00</span><span id="garden-duration">${clock(ep.duration)}</span></div><div class="audio-actions"><span id="garden-audio-status" role="status">轻触播放，听完整故事</span><button id="garden-loop" data-garden-act="loop" aria-pressed="false" aria-label="循环播放整段合成示例">↻ 循环</button></div><p class="audio-provenance">林岚 · 合成示例音频 · 播放整段故事<br>摘录尚未与音频时间逐句对齐。</p></div><details class="imagery-details"><summary>关于这张记忆意象</summary><p>这是按本段故事提前生成的演示图片。同一段故事的记忆点共享一张意象。</p><p>固定 1536 × 1024 · 3:2 横幅；奶油纸色、鼠尾草绿、灰蓝与暖金，水彩和粉彩质感。场景内容随记忆改变。</p><p>未来生成前先预览要发送的文字并确认；不自动上传录音。此处展示已生成结果，不发起模型调用。</p></details></aside></div><section class="related-memories"><h2>同一段故事里，还有……</h2>${related.map(q=>`<button data-related="${q.id}"><span>${q.title}</span><span aria-hidden="true">↗</span></button>`).join('')}</section><button class="secondary" data-garden-act="back">回到花园，继续看看</button></div>`;
  }
  function updateAudio(){
    const play=document.getElementById('garden-play');if(!play)return;
    play.textContent=audio.paused?'▶':'Ⅱ';play.setAttribute('aria-label',audio.paused?'播放整段合成示例':'暂停合成示例');play.dataset.playing=String(!audio.paused);
    const seek=document.getElementById('garden-seek'),duration=Number.isFinite(audio.duration)?audio.duration:0;
    seek.disabled=!duration||Boolean(audio.error);if(duration)seek.max=duration;seek.value=audio.currentTime;
    document.getElementById('garden-current').textContent=clock(audio.currentTime);
    if(duration)document.getElementById('garden-duration').textContent=clock(duration);
    document.getElementById('garden-audio-status').textContent=audioMessage;
    document.getElementById('garden-loop').setAttribute('aria-pressed',String(audio.loop));
  }
  function mountAudio(){
    const p=find(state.selected),src=`memory-garden/audio/${p.episode}.mp3`;
    if(audio.getAttribute('src')!==src){audio.src=src;audio.loop=false;audioMessage='轻触播放，听完整故事';}
    updateAudio();
    document.querySelector('.reverie-title')?.focus({preventScroll:true});
  }
  async function toggleAudio(){
    if(!audio.paused){audio.pause();return;}
    const epoch=++playEpoch;
    try{
      if(audio.error){audio.load();audioMessage='重新加载音频…';}
      if(audio.ended)audio.currentTime=0;
      await audio.play();
      if(epoch!==playEpoch||(page!=='reverie'&&!document.querySelector('.garden-depth[data-level="petal"]'))){audio.pause();return;}
      audioMessage='正在播放整段合成示例';
    }catch(error){if(epoch!==playEpoch)return;audioMessage=error.name==='NotAllowedError'?'请再轻触一次播放按钮':'音频暂时无法播放，点击播放可重试';}
    updateAudio();
  }
  audio.addEventListener('timeupdate',updateAudio);
  audio.addEventListener('loadedmetadata',updateAudio);
  audio.addEventListener('play',()=>{audioMessage='正在播放整段合成示例';updateAudio();});
  audio.addEventListener('pause',()=>{audioMessage=audio.ended?'这一段故事，听完了':'已暂停，可以慢慢看';updateAudio();});
  audio.addEventListener('ended',()=>{audioMessage='这一段故事，听完了';updateAudio();});
  audio.addEventListener('error',()=>{audioMessage='音频暂时无法播放，点击播放可重试';updateAudio();});
  audio.addEventListener('waiting',()=>{audioMessage='正在缓冲声音…';updateAudio();});
  audio.addEventListener('playing',()=>{audioMessage='正在播放整段合成示例';updateAudio();});
  let heroFlight;
  function pauseAudio(){++playEpoch;audio.pause();}
  function teardown(){stageAbort?.abort();observer?.disconnect();pauseAudio();MemoryImagery.close();heroFlight?.();}
  function enterScene(){
    const thumbnail=document.querySelector('.memory-bubble img'),from=thumbnail?.getBoundingClientRect();
    navigate('reverie');document.getElementById('screen').scrollTop=0;
    const target=document.querySelector('.memory-art img');
    if(!from||!target||reducedMotion())return;
    const to=target.getBoundingClientRect(),phone=document.querySelector('.phone').getBoundingClientRect();
    if(to.top>phone.bottom||from.bottom<phone.top)return;
    const flight=target.cloneNode();flight.removeAttribute('id');flight.alt='';flight.setAttribute('aria-hidden','true');flight.className='memory-flight';
    Object.assign(flight.style,{left:`${to.left}px`,top:`${to.top}px`,width:`${to.width}px`,height:`${to.height}px`});
    document.body.append(flight);target.style.visibility='hidden';
    const animation=flight.animate([{transform:`translate(${from.left-to.left}px,${from.top-to.top}px) scale(${from.width/to.width},${from.height/to.height})`,borderRadius:'40px',opacity:.85},{transform:'none',borderRadius:'22px',opacity:1}],{duration:420,easing:'cubic-bezier(.2,.75,.2,1)',fill:'both'});
    const cleanup=()=>{target.style.visibility='';flight.remove();if(heroFlight===cancel)heroFlight=null;};
    const cancel=()=>{animation.cancel();cleanup();};heroFlight=cancel;
    animation.finished.then(cleanup,cleanup);
  }
  function refresh(){document.getElementById('results').innerHTML=render(state.query);mount();}
  document.addEventListener('click',e=>{
    const b=e.target.closest('button');if(!b)return;
    if(b.dataset.memory){if(b.closest('#garden-stage')&&dragged&&e.detail!==0){dragged=false;return;}bubble(b.dataset.memory);return;}
    if(b.dataset.filter){state.filter=b.dataset.filter;state.branch=0;closeBubble();state.camera={z:1,x:0,y:0};refresh();document.querySelector(`[data-filter="${state.filter}"]`)?.focus({preventScroll:true});return;}
    if(b.dataset.related){state.selected=b.dataset.related;renderSceneChange();return;}
    if(b.dataset.gardenLayout){state.layout=b.dataset.gardenLayout;closeBubble();state.camera={z:1,x:0,y:0};refresh();document.querySelector(`[data-garden-layout="${state.layout}"]`)?.focus({preventScroll:true});return;}
    const act=b.dataset.gardenAct;if(!act)return;
    if(act==='filters'){state.filtersOpen=!state.filtersOpen;refresh();document.querySelector('[data-garden-act="filters"]')?.focus({preventScroll:true});}
    if(act==='previous-branch'||act==='next-branch'){state.branch+=act==='next-branch'?1:-1;closeBubble();state.camera={z:1,x:0,y:0};refresh();document.getElementById('garden-stage')?.focus({preventScroll:true});}
    if(act==='search'){const box=document.getElementById('archive-search');box.classList.toggle('hidden');b.setAttribute('aria-expanded',String(!box.classList.contains('hidden')));if(!box.classList.contains('hidden'))document.getElementById('query').focus();}
    if(act==='in'||act==='out'||act==='reset'){closeBubble();state.camera=act==='reset'?{z:1,x:0,y:0}:G.zoomAt(state.camera,state.camera.z+(act==='in'?.25:-.25));paintCamera();}
    if(act==='close')closeBubble(true);
    if(act==='enter')enterScene();
    if(act==='back'){state.focusReturn=true;navigate('archive');}
    if(act==='view'){state.view=state.view==='flower'?'list':'flower';closeBubble();refresh();document.querySelector('[data-garden-act="view"]')?.focus({preventScroll:true});}
    if(act==='clear'){state.branch=0;state.filter='all';state.query='';search='';document.getElementById('query').value='';refresh();document.getElementById('query').focus();}
    if(act==='play')toggleAudio();
    if(act==='loop'){audio.loop=!audio.loop;updateAudio();}
  });
  function renderSceneChange(){teardown();renderApp();document.getElementById('screen').scrollTop=0;if(!reducedMotion())document.querySelector('.reverie').animate([{opacity:0,transform:'translateY(10px)'},{opacity:1,transform:'none'}],{duration:320,easing:'ease-out'});}
  // The app calls init with its render function; avoid shadowing this module's render.
  let renderApp=()=>{};
  document.addEventListener('input',e=>{if(e.target.id==='garden-seek'&&Number.isFinite(audio.duration)){audio.currentTime=Math.max(0,Math.min(audio.duration,Number(e.target.value)));updateAudio();}});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&state.selected&&page==='archive'){closeBubble(true);e.preventDefault();}});
  document.addEventListener('visibilitychange',()=>{if(document.hidden){++playEpoch;audio.pause();}});
  window.addEventListener('pagehide',teardown);
  return {render,scene,mount,teardown,pauseAudio,detail:id=>{state.selected=id;return scene();},mountDetail:mountAudio,init:fn=>{renderApp=fn;}};
})();
