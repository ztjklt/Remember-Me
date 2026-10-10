window.MemoryImagery=(()=>{
  const M=MemoryImageryModel,{points,episodes}=MemoryGardenData;
  let storage;try{storage=window.localStorage;}catch{storage=null;}
  const choices=M.createStore(points,episodes,storage);
  const descriptions={
    E01:'雨夜的社区图书馆，木柜台旁放着备用伞，窗边亮着一盏灯。',
    E02:'冬夜靠窗的餐桌，一碗已经凉了的汤，两把椅子和柔和的室内灯光。',
    E03:'家里的厨房，一锅慢慢煨着的萝卜汤，起雾的窗，手写的旧食谱。'
  };
  const escape=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const picture=p=>`memory-garden/images/${episodes[p.episode].image}.png`;
  const dialog=document.createElement('dialog');dialog.id='imagery-dialog';dialog.className='imagery-dialog';dialog.setAttribute('aria-labelledby','imagery-heading');document.body.append(dialog);
  let draft=null,selected=null,epoch=0,returnButton=null;
  const messages=new Map();
  function render(p){
    const ep=episodes[p.episode],choice=choices.get(p),adopted=choice.status==='adopted';
    return `<section class="memory-imagery" data-memory-art="${p.id}" aria-label="记忆意象">${choice.hidden?`<div class="imagery-placeholder"><span class="imagery-small-flower" aria-hidden="true">${icon('flower')}</span><h2>让声音，先留在这里。</h2><p>这颗记忆暂不展示图片。<br>原话和声音仍在下方。</p></div>`:`<figure class="memory-art"><img src="${picture(p)}" alt="${ep.alt}" width="1536" height="1024"><figcaption><span>${adopted?'这颗记忆的意象':'本段故事的意象'}</span><span>AI 绘制 · 非历史照片</span></figcaption></figure>`}<div class="imagery-card-actions"><button class="imagery-open" data-imagery="open" data-point="${p.id}">${icon('flower')}<span>${choice.hidden?'为这一刻选一幅画':adopted?'查看意象与画风':'为这颗记忆选定意象'}</span><span aria-hidden="true">↗</span></button>${!choice.hidden?`<button class="imagery-hide" data-imagery="hide" data-point="${p.id}">只留文字与声音</button>`:''}<p class="imagery-selection-status" role="status">${escape(messages.get(p.id)||(choice.status==='stale'?'原话已更新，这张意象需要重新确认。':adopted?'已采用 · 此浏览器保存了你的示例选择':choice.hidden?'已隐藏意象，随时可以重新选择。':'同一段故事共享一幅意象；可以单独为这颗记忆采用。'))}</p></div></section>`;
  }
  function patch(p){const host=document.querySelector(`[data-memory-art="${p.id}"]`);if(host)host.outerHTML=render(p);}
  function position(){
    const phone=document.querySelector('.phone').getBoundingClientRect(),w=Math.min(phone.width-20,510);
    dialog.style.left=`${phone.left+(phone.width-w)/2}px`;dialog.style.width=`${w}px`;
    dialog.style.bottom=`${Math.max(10,innerHeight-phone.bottom+10)}px`;
    dialog.style.maxHeight=`${Math.min(innerHeight-32,phone.height-24)}px`;
  }
  function draw(){
    const p=selected,ep=episodes[p.episode],isPreview=draft.step==='preview';
    dialog.innerHTML=`<div class="imagery-sheet-head"><div><span class="garden-eyebrow">A PICTURE FOR THIS MOMENT</span><h2 id="imagery-heading" tabindex="-1">${isPreview?'是你记得的感觉吗？':'给这一刻，一幅画。'}</h2></div><button class="imagery-close" data-imagery="cancel" aria-label="关闭意象选择">×</button></div><ol class="imagery-steps" aria-label="选择进度"><li ${!isPreview?'aria-current="step"':''}>01 确认内容与画风</li><li ${isPreview?'aria-current="step"':''}>02 看图，再留下</li></ol>${isPreview?`<figure class="imagery-preview"><img id="imagery-candidate" src="${picture(p)}" alt="${ep.alt}" width="1536" height="1024"><figcaption>预生成示例 · 记忆意象</figcaption></figure><p class="imagery-target">留给「${p.title}」</p><p class="imagery-explainer">取材于《${ep.title}》这段故事。它表达氛围，画中的细节不作为记忆事实。</p><p id="imagery-loading" class="imagery-load-status" role="status">正在打开本地图片…</p><div class="imagery-sheet-footer"><button class="primary" data-imagery="adopt" disabled>采用这张意象</button><button class="text-button" data-imagery="context">返回内容确认</button></div>`:`<section class="imagery-source"><span class="imagery-caption">这颗记忆 · ${ep.year}</span><h3>${p.title}</h3><blockquote>“${p.quote}”</blockquote><p>来源：${ep.title} · 演示原稿</p></section><section class="imagery-style"><div class="imagery-style-heading"><h3>同一种温柔，不同的故事。</h3><span class="imagery-ratio">3:2</span></div><div class="imagery-palette" aria-label="奶油纸色、鼠尾草绿、灰蓝、蜜金"><i style="--swatch:#f1e9d4"></i><i style="--swatch:#8e9d82"></i><i style="--swatch:#a1b9cc"></i><i style="--swatch:#c3a166"></i><span>柔和水彩 · 自然光 · 淡淡纸纹</span></div><p class="imagery-dimensions">统一横幅 1536 × 1024，保持画幅与画风。</p><details><summary>看看这张图的画面描述</summary><p>${descriptions[p.episode]}</p><p>本次取材于整段故事；同一故事的多个记忆点可以采用同一张图。</p></details></section><p class="imagery-demo-note">Demo 使用已准备好的图片，不上传文字，也不调用生图服务。</p><div class="imagery-sheet-footer"><button class="primary" data-imagery="preview">预览示例意象</button><button class="text-button" data-imagery="cancel">先不选，继续回忆</button></div>`}`;
    position();dialog.scrollTop=0;
    dialog.querySelector('h2').focus({preventScroll:true});
    const token=++epoch,img=dialog.querySelector('#imagery-candidate');
    if(img){
      const settle=error=>{if(token!==epoch||!dialog.open)return;draft=M.resolve(draft,{width:img.naturalWidth,height:img.naturalHeight,error});
        dialog.querySelector('[data-imagery="adopt"]').disabled=!draft.ready;
        dialog.querySelector('#imagery-loading').textContent=draft.ready?'图已准备好 · 采用后仅保存此浏览器的示例选择':'图片未能打开，原来的意象仍保留。返回内容确认后可重试。';
        dialog.querySelector('.imagery-preview').classList.toggle('image-failed',!draft.ready);
      };
      img.addEventListener('load',()=>settle(false),{once:true});img.addEventListener('error',()=>settle(true),{once:true});
      if(img.complete)settle(!img.naturalWidth);
    }
  }
  function open(p){
    selected=p;draft=M.createDraft(p,episodes);returnButton=document.activeElement;
    // Open before draw so decoded, cached images can resolve immediately.
    if(!dialog.open)dialog.showModal();draw();
  }
  function close(){++epoch;if(dialog.open)dialog.close();draft=null;}
  dialog.addEventListener('close',()=>{++epoch;draft=null;
    const next=returnButton?.isConnected?returnButton:document.querySelector(`[data-imagery="open"][data-point="${selected?.id}"]`);
    next?.focus({preventScroll:true});
  });
  dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)close();}});
  document.addEventListener('click',e=>{
    const b=e.target.closest('[data-imagery]');if(!b)return;
    const action=b.dataset.imagery,p=points.find(p=>p.id===b.dataset.point)||selected;
    if(action==='open'){MemoryGarden.pauseAudio();open(p);}
    if(action==='hide'){const result=choices.hide(p);messages.set(p.id,result.persisted?'已隐藏意象。可以随时重新选择，原话与声音不变。':'当前已隐藏；浏览器无法保存，刷新后将恢复。');patch(p);document.querySelector(`[data-imagery="open"][data-point="${p.id}"]`)?.focus({preventScroll:true});}
    if(action==='cancel')close();
    if(action==='preview'&&draft){draft=M.preview(draft);draw();}
    if(action==='context'&&draft){draft=M.createDraft(selected,episodes);draw();}
    if(action==='adopt'&&draft){
      if(!M.canAdopt(draft,selected,episodes))return;
      const result=choices.adopt(selected);messages.set(selected.id,result.persisted?'这幅意象，已留在这颗记忆里。此浏览器已保存。':'本次已采用；浏览器无法保存，刷新后将恢复。');
      patch(selected);close();
    }
  });
  window.addEventListener('resize',()=>{if(dialog.open)position();});
  return {render,close};
})();
