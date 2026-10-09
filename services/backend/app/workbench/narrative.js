'use strict';
// All text from models and users is rendered with textContent, never HTML.
const NarrativeView = (() => {
  const names={story:'故事',person:'人物',observation:'情境观察',letter:'给你的话',style:'表达范例'};
  const status={pending:'待核对',confirmed:'本人已核对',stale:'来源已变化',rejected:'已撤回',conflicted:'存在不同说法'};
  const fields=['kind','title','text','evidence_ids','facets','time_text','place_text','aliases','same_event','recipient_label'];
  const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  const button=(text,fn)=>{const e=node('button',text);e.type='button';e.addEventListener('click',()=>Promise.resolve().then(fn).catch(err=>window.dispatchEvent(new CustomEvent('narrative-error',{detail:err.message}))));return e;};
  let editor=null,selected=0,query='',review=false,identity='',callbacks=null,latest=null,signature='';
  function relatedStories(record,visibleRecords){
    if(!['person','observation'].includes(record.kind)||record.status!=='confirmed'||!record.source_valid)return [];
    const refs=new Set(record.evidence_ids||[]);
    return visibleRecords.filter(r=>r.kind==='story'&&r.status==='confirmed'&&r.source_valid&&(r.evidence_ids||[]).some(id=>refs.has(id)));
  }
  function clear(){editor?.remove();editor=null;identity='';selected=0;query='';review=false;latest=null;callbacks=null;signature='';document.getElementById('narrativeViews')?.replaceChildren();}
  function edit(record,split=false){
    editor?.remove();const dialog=node('dialog');editor=dialog;dialog.className='narrative-editor';
    const form=node('form');form.method='dialog';dialog.append(form);form.append(node('h2',split?'拆出一段故事':'让故事更完整'));
    form.append(button('返回',()=>{dialog.close();dialog.remove();editor=null;}));
    const values={};
    function input(key,label,value,tag='input'){const wrap=node('label',label);const e=node(tag);e.value=value||'';wrap.append(e);form.append(wrap);values[key]=e;return e;}
    const type=input('kind','内容类型',record.kind||'story','select');
    Object.entries(names).forEach(([value,label])=>{const option=node('option',label);option.value=value;type.append(option);});type.value=record.kind||'story';type.disabled=!!record.id;
    input('title','标题',record.title);input('text','内容（寄语和表达范例须逐字来自本人原话）',record.text,'textarea');
    input('time_text','发生时间原文，可保留不确定',record.time_text);input('place_text','地点原文',record.place_text);
    input('aliases','同一个人的称呼，用顿号分隔',(record.aliases||[]).join('、'));input('recipient_label','想留给谁（不会自动授权）',record.recipient_label);
    const same=input('same_event','这些来源明确讲的是同一次事件');same.type='checkbox';same.checked=!!record.same_event;
    const chosen=new Set(record.facets||['EXPERIENCE']),refs=new Set(record.evidence_ids||[]);
    form.append(node('h3','内容维度'));
    for(const facet of latest.facets){const label=node('label',facet.title),check=node('input');check.type='checkbox';check.checked=chosen.has(facet.id);check.onchange=()=>check.checked?chosen.add(facet.id):chosen.delete(facet.id);label.prepend(check);form.append(label);}
    form.append(node('h3','选择真实来源'),node('p','拆分时只选要移入新故事的部分；原音和授权保持不变。'));
    for(const source of latest.source_evidence){const label=node('label',source.excerpt),check=node('input');check.type='checkbox';check.checked=refs.has(source.evidence_id);check.onchange=()=>check.checked?refs.add(source.evidence_id):refs.delete(source.evidence_id);label.prepend(check);form.append(label);}
    const error=node('p',undefined,'error');error.setAttribute('role','alert');form.append(error);
    const save=button('保存为待核对内容',async()=>{save.disabled=true;try{
      const body=Object.fromEntries(Object.entries(values).map(([k,e])=>[k,e.value]));body.same_event=same.checked;body.aliases=values.aliases.value.split('、').map(s=>s.trim()).filter(Boolean);body.facets=[...chosen];body.evidence_ids=[...refs];
      if(record.id)body.revision=record.revision;
      await callbacks.mutate('/records'+(record.id?'/'+encodeURIComponent(record.id):'')+(split?'/split':''),split||!record.id?'POST':'PUT',body);
      dialog.close();dialog.remove();editor=null;
    }catch(e){error.textContent=e.message;}finally{save.disabled=false;}});form.append(save);form.addEventListener('submit',e=>e.preventDefault());document.body.append(dialog);dialog.showModal();
  }
  function render(box,data,cb){
    const nextIdentity=cb.identity;if(identity&&identity!==nextIdentity)clear();identity=nextIdentity;callbacks=cb;latest=data;
    const nextSignature=JSON.stringify([identity,data,selected,review]);if(signature===nextSignature&&box.childElementCount)return;signature=nextSignature;box.replaceChildren();
    const controls=node('div',undefined,'narrative-controls');box.append(controls);
    const tabs=node('div',undefined,'narrative-tabs');tabs.setAttribute('role','group');tabs.setAttribute('aria-label','了解这个人的四种视角');
    data.views.forEach((v,i)=>{const b=button(v.title,()=>{selected=i;review=false;render(box,data,cb);});b.setAttribute('aria-pressed',String(selected===i&&!review));tabs.append(b);});controls.append(tabs);
    const search=node('input');search.placeholder='找故事、人名或一件旧物';search.setAttribute('aria-label',search.placeholder);search.value=query;search.oninput=()=>{query=search.value;for(const article of box.querySelectorAll('[data-search]'))article.hidden=!!query&&!article.dataset.search.includes(query);};controls.append(search);
    if(data.role==='owner'){
      const available=[...new Set(data.source_evidence.map(e=>e.episode_id))],chosenEpisodes=new Set(available.slice(0,2));
      const scope=node('details');scope.append(node('summary','选择本次对照的录音 · 默认前两段'));
      for(const id of available){const source=data.source_evidence.find(e=>e.episode_id===id),label=node('label',source.excerpt.slice(0,70)),check=node('input');check.type='checkbox';check.checked=chosenEpisodes.has(id);check.onchange=()=>check.checked?chosenEpisodes.add(id):chosenEpisodes.delete(id);label.prepend(check);scope.append(label);}controls.append(scope);
      controls.append(button(review?'返回已核对内容':'核对整理建议',()=>{review=!review;render(box,data,cb);}),button('从原文整理 / 留下寄语',()=>edit({})));
      const label=node('label','我同意将已核对的有效文字交由云端组织故事。');const consent=node('input');consent.type='checkbox';label.prepend(consent);controls.append(label);
      controls.append(button('整理选定讲述',async()=>{if(!consent.checked)throw Error('请先确认本次云端文字整理。');if(!chosenEpisodes.size)throw Error('请先选择来源录音。');await cb.suggest([...chosenEpisodes]);}));
      if(selected===3){const toggle=node('input');toggle.type='checkbox';toggle.checked=data.style.enabled;const label=node('label','允许使用已确认的表达范例；回应始终标注系统生成。');label.prepend(toggle);toggle.onchange=async()=>{try{await cb.mutate('/style','PUT',{enabled:toggle.checked,revision:data.style.revision});}catch(e){toggle.checked=data.style.enabled;window.dispatchEvent(new CustomEvent('narrative-error',{detail:e.message}));}};controls.append(label);}
    }
    const ids=new Set(data.views[selected]?.records||[]);
    const rows=data.records.filter(r=>(review?['pending','stale'].includes(r.status):ids.has(r.id)));
    const garden=node('div',undefined,'story-clusters');box.append(garden);
    if(!rows.length)garden.append(node('p',review?'暂时没有需要核对的建议。':'这里尚无已核对的材料。原有录音与记忆仍可在档案中查看。'));
    for(const row of rows){
      const article=node('article',undefined,'story-cluster');article.dataset.recordId=row.id;article.dataset.search=row.title+row.text+row.place_text+(row.aliases||[]).join(' ');article.hidden=!!query&&!article.dataset.search.includes(query);
      const mark=node('img');mark.src='/brand/v2/svg/mark-light.svg';mark.alt='';mark.width=40;mark.height=40;article.append(mark,node('small',names[row.kind]+' · '+(status[row.status]||row.status)),node('h3',row.title),node('p',row.text));
      if(row.time_text)article.append(node('p','发生时间：'+row.time_text));if(row.place_text)article.append(node('p','当时地点：'+row.place_text));if(row.recipient_label)article.append(node('p','想留给：'+row.recipient_label+'；仍按原音授权。'));
      const detail=node('details');detail.append(node('summary','为什么这样整理 · 听原声'));
      for(const e of row.evidence){detail.append(node('blockquote',e.excerpt),node('small',e.source_type==='CALIBRATION'?'本人书面补充 / 修订':'核对文字；尚非音频逐字对齐'),button('打开来源与完整原音',()=>cb.open(e.episode_id)));}
      article.append(detail);
      const linked=relatedStories(row,data.records);
      if(linked.length){article.append(node('h4','从这些故事继续了解'),node('small','这些内容共用原文依据；不代表系统判定了关系或亲密程度。'));
        for(const story of linked)article.append(button('读故事：'+story.title,()=>focusRecord(story.id)));}
      if(data.role==='owner'){
        if(row.status==='pending')article.append(button('核对无误，确认整理',()=>cb.mutate('/records/'+row.id+'/confirm','POST',{revision:row.revision})));
        article.append(button('编辑 / 移出来源',()=>edit(row)),button('撤回整理',()=>cb.mutate('/records/'+row.id+'/reject','POST',{revision:row.revision})));
        if(row.kind==='story')article.append(button('拆出新故事',()=>edit(row,true)));
        article.append(button('查看变化历史',async()=>{const result=await cb.read('/records/'+row.id+'/history');const h=node('div');for(const item of result.items)h.append(node('p',`版本 ${item.revision} · ${item.action} · ${item.record.title}`));article.append(h);}));
        if(row.revision>2)article.append(button('恢复旧内容再核对',()=>cb.mutate('/records/'+row.id+'/undo','POST',{revision:row.revision})));
      }
      garden.append(article);
    }
    if(selected===2)for(const u of data.understandings){const item=node('article',undefined,'understanding');item.append(node('h3',u.statement),node('p','适用情境：'+u.context),node('small',u.label+' · '+(status[u.status]||u.status)));const details=node('details');details.append(node('summary','支持、例外与依据'),node('p','已确认独立事件：'+u.independent_events+'；数量不是准确率。'));for(const [label,sources] of [['支持',u.evidence],['例外 / 反例',u.counter_evidence]])for(const e of sources)details.append(node('p',label+'：'+e.excerpt),button('查看依据',()=>cb.open(e.episode_id)));item.append(details);box.append(item);}
    box.append(node('p',data.notice,'muted'));
  }
  function focusRecord(id){
    if(!latest||!callbacks)return;const row=latest.records.find(r=>r.id===id);if(!row)return;
    selected=Math.max(0,latest.views.findIndex(v=>v.records.includes(id)));review=row.status!=='confirmed';query='';signature='';
    const box=document.getElementById('narrativeViews');render(box,latest,callbacks);
    const article=[...box.querySelectorAll('[data-record-id]')].find(e=>e.dataset.recordId===id);
    if(article){article.tabIndex=-1;article.focus({preventScroll:true});article.scrollIntoView({block:'start'});}
  }
  return {render,clear,focusRecord,relatedStories};
})();
