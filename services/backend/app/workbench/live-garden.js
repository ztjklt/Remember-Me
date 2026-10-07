/* PR85 botanical photographs, real API bindings. No fixture stories or audio. */
(function(root){
  function model(stories){return stories.filter(s=>s.status==='ready'&&!s.unavailable).map(s=>({
    episodeId:s.episode_id,date:s.recorded_at,memories:s.memories.filter(m=>m.review_state==='active').map(m=>({
      id:m.memory_item_id,text:m.content,episodeId:s.episode_id})),story:s
  })).filter(s=>s.memories.length);}
  let page=0,signature='',generation=0;
  function render(host,stories,open){
    const rows=model(stories),key=JSON.stringify(rows);if(signature===key&&host.childElementCount)return;
    signature=key;generation++;page=Math.min(page,Math.max(0,Math.ceil(rows.length/3)-1));
    host.replaceChildren();
    const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;};
    const heading=el('div',null,'garden-heading');heading.append(el('h2','留下的日子，慢慢开花'),el('p',rows.length?`${rows.length} 段故事 · ${rows.reduce((n,r)=>n+r.memories.length,0)} 条有效记忆`:'花园还在等第一段故事','muted'));host.append(heading);
    if(!rows.length){host.append(el('p','完成核对和整理后，故事会出现在这里。花朵是装饰，数量只代表已保存的故事。','garden-empty'));return;}
    const scene=el('div',null,'live-garden-scene');scene.setAttribute('aria-label','记忆花园，每一枝对应一段真实故事');
    for(const [i,row] of rows.slice(page*3,page*3+3).entries()){
      const plant=el('article',null,'living-story living-story-'+i);
      plant.dataset.episodeId=row.episodeId;
      const stem=el('img',null,'living-stem');stem.src='/brand/v21/stem.png';stem.alt='';
      const bloom=el('img',null,'living-bloom');bloom.src='/brand/v20/bloom-'+(i===1?'side':'cupped')+'.png';bloom.alt='';
      const enter=el('button',null,'flower-enter');enter.setAttribute('aria-label','查看故事：'+row.memories[0].text);
      enter.append(bloom);enter.onclick=()=>open(row.story);plant.append(stem,enter);
      const label=el('button',row.memories[0].text,'flower-caption');label.onclick=()=>open(row.story);
      const list=el('div',null,'petal-links');list.setAttribute('aria-label','这段故事中的记忆');
      for(const memory of row.memories){const link=el('button',memory.text,'petal-link');link.dataset.memoryId=memory.id;link.onclick=()=>open(row.story,memory.id);list.append(link);}
      plant.append(label,el('small',new Date(row.date).toLocaleDateString('zh-CN')),list);scene.append(plant);
    }
    host.append(scene);
    if(rows.length>3){const controls=el('div',null,'actions');for(const [text,delta]of[['上一枝',-1],['下一枝',1]]){
      const b=el('button',text);b.disabled=page+delta<0||page+delta>=Math.ceil(rows.length/3);b.onclick=()=>{page+=delta;signature='';render(host,stories,open);};controls.append(b);
    }controls.append(el('small',`第 ${page+1} / ${Math.ceil(rows.length/3)} 页`));host.append(controls);}
  }
  function clear(){signature='';page=0;generation++;}
  const api={model,render,clear};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.LiveGarden=api;
})(typeof window==='undefined'?{}:window);
