import {SessionClient} from './api.js';
import {availableStories,projectGarden,currentEvidence,personRows,confirmedUnderstandings,chooseSpace,flowerForm,domainFacet} from './model.js';
import {facetTitles,viewTitles,viewFacets} from './native-labels.js';

const $=id=>document.getElementById(id),api=new SessionClient();
const state={config:null,space:null,stories:[],narrative:{},clusters:[],understandings:[],page:'garden',list:false,section:'views',view:0,facet:'',personIndex:0,understandingIndex:0,chat:[],mode:'evidence',busy:false,refreshing:false,updated:0,voice:null};
const root=()=>'/api/v1/workbench/subjects/'+encodeURIComponent(state.space.subject_id);
const subjectRoot=()=>'/api/v1/subjects/'+encodeURIComponent(state.space.subject_id);
const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const image=(file,cls='')=>{const n=node('img',undefined,cls);n.src='/app/assets/'+file+'.png';n.alt='';return n;};
function report(text,error=false){$('notice').replaceChildren(node('span',text),button('收起',()=>{$('notice').hidden=true;},'quiet'));$('notice').hidden=false;$('notice').dataset.error=String(error);}
function handle(e){if(e.name==='AbortError')return;if(e.status===401){reset();report('登录已失效，请重新进入陈守义的空间。',true);}else report(e.message || '连接中断，请稍后重试。',true);}
function button(text,action,cls='quiet'){const b=node('button',text,cls);b.type='button';b.onclick=async()=>{b.disabled=true;try{await action();}catch(e){handle(e);}finally{b.disabled=false;}};return b;}
function bind(id,event,action){$(id).addEventListener(event,e=>{e.preventDefault();Promise.resolve().then(()=>action(e)).catch(handle);});}
function pressed(id,value){$(id).setAttribute('aria-pressed',String(value));}
const short=(text,n=45)=>text.length>n?text.slice(0,n)+'…':text;
const date=text=>text?new Date(text).toLocaleDateString('zh-CN',{month:'long',day:'numeric'}):'日期未记录';
let mediaTicket=0,detailTicket=0,mediaURLs=[],selection=null,petalPage=0;
function stopMedia(){mediaTicket++;document.querySelectorAll('audio').forEach(a=>{a.pause();a.removeAttribute('src');a.load();a.remove();});mediaURLs.forEach(u=>URL.revokeObjectURL(u));mediaURLs=[];}
function closeDetail(){detailTicket++;stopMedia();$('detail').close();$('detailContent').replaceChildren();selection=null;}
function reset(){api.reset();stopMedia();closeDetail();state.space=null;state.stories=[];state.narrative={};state.clusters=[];state.chat=[];state.busy=false;state.refreshing=false;state.updated=0;$('refresh').disabled=false;$('questionForm').reset();$('workspace').hidden=true;$('navigation').hidden=true;$('refresh').hidden=true;$('welcome').hidden=false;$('identity').textContent='记忆有来处，陪伴有温度';for(const id of ['messages','gardenContent','personContent','understandings','recordings'])$(id).replaceChildren();sessionStorage.removeItem('remember-web-space');sessionStorage.removeItem('remember-web-demo');}
function switchPage(page){if(!['garden','person','dialogue','record'].includes(page))page='garden';stopMedia();state.page=page;for(const p of ['garden','person','dialogue','record'])$(p).hidden=p!==page;document.querySelectorAll('[data-page]').forEach(b=>b.setAttribute('aria-current',b.dataset.page===page?'page':'false'));history.replaceState(null,'','#'+page);window.scrollTo({top:0,behavior:'instant'});}
async function connect(){
  const spaces=await api.request('/api/v1/workbench/spaces');
  const space=chooseSpace(spaces.items,state.config.demo_subject_id);
  if(!space){reset();$('entryState').textContent='当前登录不是陈守义的独立空间，请通过上方按钮进入。';return;}
  state.space=space;sessionStorage.setItem('remember-web-space',space.subject_id);
  $('identity').textContent=space.display_name;$('welcome').hidden=true;$('workspace').hidden=false;$('navigation').hidden=false;$('refresh').hidden=false;
  switchPage(location.hash.slice(1)||'garden');await refresh(true);
}
async function refresh(manual=false){
  if(!state.space||state.busy||state.refreshing)return;
  const epoch=api.epoch;state.refreshing=true;$('refresh').disabled=true;
  try {
    const spaces=await api.request('/api/v1/workbench/spaces');
    if(!chooseSpace(spaces.items,state.space.subject_id)){reset();report('当前空间的访问许可已变化，请重新进入。',true);return;}
    const [stories,narrative,voice]=await Promise.all([api.request(root()+'/stories'),api.request(root()+'/narrative'),api.request(subjectRoot()+'/voice/profile').catch(e=>{if([403,404].includes(e.status))return null;throw e;})]);
    if(epoch!==api.epoch)return;
    const changed=JSON.stringify(stories.items)!==JSON.stringify(state.stories)||JSON.stringify(narrative)!==JSON.stringify(state.narrative);
    state.stories=stories.items||[];state.narrative=narrative;state.voice=voice;
    state.clusters=projectGarden(state.stories,narrative);state.understandings=confirmedUnderstandings(state.stories,narrative);
    // Saved responses are re-authorized; revoked answers never linger in this view.
    const current=await Promise.all(state.chat.map(async m=>{if(!m.answer?.answer_id)return m;try{return {...m,answer:await api.request(subjectRoot()+'/twin/answers/'+encodeURIComponent(m.answer.answer_id))};}catch(e){if([403,404,409].includes(e.status))return {...m,answer:null,error:'这条回答的来源或授权已变化，请重新提问。'};throw e;}}));
    if(epoch!==api.epoch)return;state.chat=current;
    if(changed||manual){closeDetail();renderGarden();renderPerson();renderRecordings();renderChat();}
    state.updated=Date.now();$('syncTime').textContent='上次同步：'+new Date(state.updated).toLocaleTimeString('zh-CN')+' · 与 App 共用后端，无本地记忆副本';
  }catch(e){if(epoch===api.epoch){closeDetail();state.stories=[];state.narrative={};state.clusters=[];state.understandings=[];state.chat=[];renderGarden();renderPerson();renderRecordings();renderChat();handle(e);}}finally{if(epoch===api.epoch){state.refreshing=false;$('refresh').disabled=false;}}
}
function renderGarden(){
  const rows=state.clusters,query=$('search').value.trim().toLocaleLowerCase();
  const visible=rows.filter(c=>!query||(c.title+' '+c.petals.map(p=>p.content+' '+p.evidence.map(e=>e.excerpt).join(' ')).join(' ')).toLocaleLowerCase().includes(query));
  const total=rows.reduce((n,r)=>n+r.petals.length,0);
  $('gardenStats').textContent=`${rows.length} 段故事 · ${total} 片记忆${query?' · 找到 '+visible.length+' 段':''}`;
  pressed('gardenMode',!state.list);pressed('listMode',state.list);
  const box=$('gardenContent');box.replaceChildren();
  if(!visible.length){box.append(node('p',query?'还没找到这句话，试试别的词。':'完成文字核对和整理后，故事会在这里慢慢留下。','empty'));return;}
  const meadow=node('div',undefined,state.list?'story-list':'garden-meadow');box.append(meadow);
  for(const c of visible){
    const form='rm_garden_flower_'+flowerForm(c.id);
    if(state.list){const b=button('',()=>openCluster(c),'list-story'),copy=node('span',c.title);copy.append(node('small',`${c.petals.length} 片记忆 · ${date(c.date)} · ${c.organized?'已核对故事':'系统整理'}`));b.append(image(form),copy,node('b','›'));meadow.append(b);continue;}
    const plant=node('article',undefined,'plant'),visual=button('',()=>openCluster(c),'plant-visual');visual.setAttribute('aria-label','打开故事：'+c.title);visual.append(image('rm_garden_stem','stem'),image(form,'bloom'));
    const caption=button(c.title,()=>openCluster(c),'plant-caption');caption.append(node('small',`${c.petals.length} 片记忆 · ${date(c.date)}`));plant.append(visual,caption);meadow.append(plant);
  }
}
function showDetail(){if(!$('detail').open)$('detail').showModal();$('detail').scrollTop=0;}
function openCluster(c){stopMedia();selection=c;petalPage=0;renderCluster();showDetail();}
function renderCluster(){
  const c=selection;if(!c)return;$('backDetail').hidden=true;
  const box=$('detailContent');box.replaceChildren(node('p',c.organized?'本人已核对的故事':'系统整理 · 来自已核对讲述','eyebrow'),node('h2',c.title),node('p','一片花瓣，一段值得停留的瞬间。','muted'));
  const scene=node('div',undefined,'petal-garden');scene.append(image('rm_garden_flower_'+flowerForm(c.id)));
  c.petals.slice(petalPage*5,petalPage*5+5).forEach((p,i)=>{const b=button('',()=>openPetal(p),'petal');b.append(node('small','记忆 '+(petalPage*5+i+1)),node('span',short(p.content,25)));b.setAttribute('aria-label','阅读记忆：'+p.content);scene.append(b);});box.append(scene);
  const pages=Math.ceil(c.petals.length/5);
  if(pages>1){const bar=node('div',undefined,'detail-paging'),prev=button('‹ 上一组',()=>{petalPage--;renderCluster();}),next=button('下一组 ›',()=>{petalPage++;renderCluster();});prev.disabled=petalPage===0;next.disabled=petalPage>=pages-1;bar.append(prev,node('span',`${petalPage+1} / ${pages} 组`),next);box.append(bar);}
  const list=node('details',undefined,'petal-list');list.append(node('summary','用列表阅读这些记忆'));c.petals.forEach(p=>list.append(button(p.content,()=>openPetal(p))));box.append(list);
  c.episodes.forEach((id,i)=>box.append(button('听完整讲述'+(c.episodes.length>1?' '+(i+1):''),()=>openSource(id),'source-link')));
}
function evidenceBlock(rows,host){for(const e of rows){host.append(node('blockquote',e.excerpt));host.append(node('small',e.source_type==='CALIBRATION'?'书面补充 / 修订；不作录音逐字定位':'核对文字 · 可回听完整讲述'));host.append(button('查看来源与原音',()=>openSource(e.episode_id),'source-link'));}}
function openPetal(p){stopMedia();const box=$('detailContent');box.replaceChildren(node('p',p.label,'eyebrow'),node('p',p.content,'detail-copy'),node('h3','这条记忆从哪里来'));evidenceBlock(p.evidence,box);$('backDetail').hidden=!selection;showDetail();}
async function openSource(id){
  stopMedia();const epoch=api.epoch,ticket=++detailTicket;
  const fresh=await api.request(root()+'/stories');if(epoch!==api.epoch||ticket!==detailTicket)return;
  const story=availableStories(fresh.items||[]).find(s=>s.episode_id===id);
  if(!story){closeDetail();await refresh(true);throw Error('这段来源已不可读取，内容已重新同步。');}
  const box=$('detailContent');box.replaceChildren(node('p','完整来源 · '+date(story.recorded_at),'eyebrow'),node('h2','听他慢慢讲'),node('p','陈守义 · 虚构演示资料，原音为合成声音。','fine'));
  const audioBox=node('div');box.append(button('播放完整原音',()=>playSource(id,audioBox),'primary'),audioBox,node('h3','已核对文字'),node('p',story.transcript||'暂无可读文字。','source-text'));$('backDetail').hidden=!selection;showDetail();
}
async function playSource(id,host){
  stopMedia();const ticket=mediaTicket,epoch=api.epoch;
  const blob=await api.request(root()+'/stories/'+encodeURIComponent(id)+'/audio',{audio:true});
  const fresh=await api.request(root()+'/stories');
  if(!availableStories(fresh.items||[]).some(s=>s.episode_id===id))throw Error('来源许可已变化，请重新同步。');
  if(ticket!==mediaTicket||epoch!==api.epoch||!$('detail').open)return;await audioElement(blob,host,'陈守义这段讲述的完整原音');
}
async function audioElement(blob,host,label){const audio=node('audio');audio.controls=true;audio.preload='metadata';audio.setAttribute('aria-label',label);const url=URL.createObjectURL(blob);mediaURLs.push(url);audio.src=url;host.append(audio);await audio.play().catch(()=>report('声音已准备好，请点击播放器播放。'));}
function personData(){
  const records=personRows(state.stories,state.narrative).map(r=>({id:r.id,title:r.title,text:r.text,facets:r.facets||[],label:'已确认的整理',evidence:r.evidence}));
  // Preserve the distinction between confirmed narrative and extracted memories.
  const memories=state.clusters.flatMap(c=>c.petals).map(p=>({id:p.id,title:facetTitles[domainFacet[p.domain]]||'讲述里的记忆',text:p.content,facets:[domainFacet[p.domain]].filter(Boolean),label:p.label,evidence:p.evidence}));
  return [...records,...new Map(memories.map(m=>[m.id,m])).values()];
}
function pager(index,size,change){const bar=node('div',undefined,'paging'),prev=button('‹',()=>change(index-1)),next=button('›',()=>change(index+1));prev.setAttribute('aria-label','上一条');next.setAttribute('aria-label','下一条');prev.disabled=index<=0;next.disabled=index>=size-1;bar.append(prev,node('span',`${index+1} / ${size}`),next);return bar;}
function renderPerson(){
  const us=state.understandings,ub=$('understandings');ub.replaceChildren();
  if(us.length){state.understandingIndex=Math.min(state.understandingIndex,us.length-1);const u=us[state.understandingIndex],card=node('article',undefined,'understanding'),heading=node('div',undefined,'card-heading');heading.append(node('p','已确认的理解','eyebrow'),pager(state.understandingIndex,us.length,i=>{state.understandingIndex=i;renderPerson();}));card.append(heading,node('blockquote',u.statement),button('查看情境与来源 ↗',()=>{selection=null;const box=$('detailContent');box.replaceChildren(node('p','已确认的理解','eyebrow'),node('p',u.statement,'detail-copy'),node('h3','适用情境'),node('p',u.context));evidenceBlock(u.evidence,box);if(u.counter_evidence?.length){box.append(node('h3','例外 / 反例'));evidenceBlock(u.counter_evidence,box);}$('backDetail').hidden=true;showDetail();}));ub.append(card);}
  pressed('viewsMode',state.section==='views');pressed('facetsMode',state.section==='facets');
  const filters=$('personFilters'),box=$('personContent'),all=personData();filters.replaceChildren();box.replaceChildren();
  if(state.section==='views')viewTitles.forEach((title,i)=>{const b=button(title,()=>{state.view=i;state.personIndex=0;renderPerson();});b.setAttribute('aria-pressed',String(state.view===i));filters.append(b);});
  else if(state.facet){filters.append(button('‹ 全部记忆侧面',()=>{state.facet='';state.personIndex=0;renderPerson();}),node('span',facetTitles[state.facet]));}
  else {const grid=node('div',undefined,'facet-grid');for(const [id,title] of Object.entries(facetTitles)){const rows=all.filter(r=>r.facets.includes(id)),b=button('',()=>{state.facet=id;state.personIndex=0;renderPerson();},'facet-card');b.append(node('strong',title),node('small',rows.length?short(rows[0].text,52):'这里还在等一段讲述'),node('span',`${rows.length} 条可阅读内容`,'count'));grid.append(b);}box.append(grid);return;}
  const rows=all.filter(r=>state.section==='facets'?r.facets.includes(state.facet):r.facets.some(f=>viewFacets[state.view].includes(f)));
  if(!rows.length){box.append(node('p','这个侧面还没有可阅读的内容。新的讲述核对后，会从同一后端同步到这里。','empty'));return;}
  state.personIndex=Math.min(state.personIndex,rows.length-1);const row=rows[state.personIndex],card=node('article',undefined,'reading-card');card.append(node('p',row.label,'eyebrow'),node('h3',row.title),node('p',row.text,'main-text'));
  const footer=node('footer');footer.append(button('回到这段故事的来源 ↗',()=>{selection=null;openPetal({content:row.text,label:row.label,evidence:row.evidence});}),pager(state.personIndex,rows.length,i=>{state.personIndex=i;renderPerson();}));card.append(footer);box.append(card);
  let touchX=null,touchY=null;card.addEventListener('touchstart',e=>{touchX=e.touches[0].clientX;touchY=e.touches[0].clientY;},{passive:true});card.addEventListener('touchend',e=>{if(touchX===null)return;const dx=e.changedTouches[0].clientX-touchX,dy=e.changedTouches[0].clientY-touchY;if(Math.abs(dx)>70&&Math.abs(dx)>Math.abs(dy)*1.5){const i=state.personIndex+(dx<0?1:-1);if(i>=0&&i<rows.length){state.personIndex=i;renderPerson();}}touchX=null;},{passive:true});
}
function renderRecordings(){const box=$('recordings');box.replaceChildren();const list=node('div',undefined,'story-list');for(const s of availableStories(state.stories)){const b=button('',()=>{selection=null;return openSource(s.episode_id);},'list-story');b.append(image('rm_garden_flower_side'),node('span',short(s.transcript||'已核对的讲述',60)),node('small',date(s.recorded_at)));list.append(b);}box.append(list);}
function renderChat(){
  pressed('evidenceMode',state.mode==='evidence');pressed('personaMode',state.mode==='persona');$('modeHint').textContent=state.mode==='evidence'?'问往事：从已有讲述查找事实，保留原话与来源。':'聊一聊：参考已确认的情境理解生成回应，不编造共同经历。';
  const box=$('messages');box.replaceChildren();
  if(!state.chat.length)box.append(node('p','不必急着说完。\n从你想了解的一件小事开始。','chat-intro'));
  for(const m of state.chat){const user=node('article',undefined,'message user');user.append(node('small','你'),node('div',m.question,'answer-text'));box.append(user);const reply=node('article',undefined,'message assistant');box.append(reply);
    if(!m.answer){reply.append(node('small',m.error?'这一轮尚未完成':'正在翻看已核对的记忆'),node('p',m.error||'稍等，让我想一想…','answer-text'));if(m.error)reply.append(button('重新填写这句话',()=>{$('question').value=m.question;$('question').focus();}));continue;}
    const a=m.answer;reply.append(node('small',a.response_type==='UNKNOWN'?'还没有足够的记录':a.mode==='persona'?'AI 分身 · 基于已确认的理解生成':a.response_type==='ORIGINAL'?'来自讲述原话':'AI 分身 · 有来源的回答'),node('div',a.answer,'answer-text'));
    const refs=node('details');refs.append(node('summary','查看回答依据'+((a.evidence||[]).length?' · '+a.evidence.length+' 处':'')));evidenceBlock(a.evidence||[],refs);
    for(const u of state.understandings.filter(u=>(a.understanding_ids||[]).includes(u.candidate_id))){refs.append(node('h3','参考的已确认理解'),node('p',u.statement),node('p','适用情境：'+u.context));}
    if(!(a.evidence||[]).length)refs.append(node('p','当前记录未提供足够依据；不会补写缺失的事实。'));
    if(a.model_version)refs.append(node('small','模型版本：'+a.model_version));reply.append(refs);
    if(state.voice?.can_synthesize&&a.answer_id&&a.response_type!=='UNKNOWN')reply.append(button('听这条回答',()=>playAnswer(a,reply)));
  }
  $('send').disabled=state.busy;$('clearChat').disabled=state.busy;
  const choices=state.mode==='evidence'?['第一次独立开十二路是哪一年？','喜欢喝浓茶还是淡茶？','茉莉花是哪一年收到的？']:['我今天很累，不太想说话。','周末去吃面，可以给我泡浓茶吗？','如果今天还有急事，也留到明天吗？'];
  $('suggestions').replaceChildren(...choices.map(q=>button(q,()=>{$('question').value=q;$('question').focus();})));
}
async function playAnswer(answer,host){stopMedia();const ticket=mediaTicket;const result=await api.request(subjectRoot()+'/twin/answers/'+encodeURIComponent(answer.answer_id)+'/speech',{method:'POST'});if(result.status!=='ready'||!result.asset_id)throw Error('声音尚未准备好，请稍后重试。');const blob=await api.request(subjectRoot()+'/voice/assets/'+encodeURIComponent(result.asset_id)+'/audio',{audio:true});await api.request(subjectRoot()+'/twin/answers/'+encodeURIComponent(answer.answer_id));const profile=await api.request(subjectRoot()+'/voice/profile');if(!profile.can_synthesize)throw Error('声音许可已变化。');if(ticket===mediaTicket)await audioElement(blob,host,'AI 分身合成回答');}
async function ask(){
  if(state.busy)return;if(state.refreshing)throw Error('正在同步最新资料，请稍后再发送。');const question=$('question').value.trim();if(!question)return;
  if(!$('cloudConsent').checked)throw Error('请先勾选本次云端文字处理。');
  const epoch=api.epoch,mode=state.mode,entry={question,answer:null};state.chat.push(entry);state.busy=true;$('question').value='';stopMedia();renderChat();
  try{
    let consent;
    if(state.space.role==='owner'){const items=await api.request('/api/v1/consents?subject_id='+encodeURIComponent(state.space.subject_id));consent=items.find(c=>c.scope==='CLOUD_TWIN'&&c.status==='granted')?.consent_id;if(!consent)consent=(await api.request('/api/v1/consents',{method:'POST',body:{subject_id:state.space.subject_id,scope:'CLOUD_TWIN'}})).consent_id;}
    else {const grants=await api.request(root()+'/grants');consent=(grants.items||[]).find(g=>g.cloud_processing_allowed)?.grant_id;}
    if(!consent)throw Error('当前身份尚未获得云端问答许可。');
    const answer=await api.request(subjectRoot()+'/twin/answers',{method:'POST',body:{question,mode,cloud_consent_id:consent}});if(epoch===api.epoch)entry.answer=answer;
  }catch(e){if(epoch===api.epoch){entry.error=e.name==='AbortError'?'本轮等待超时，请重试。':e.message;if(e.status===401)handle(e);}}
  finally{if(epoch===api.epoch){state.busy=false;renderChat();$('messages').lastElementChild?.scrollIntoView({block:'nearest',behavior:'smooth'});}}
}

document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>switchPage(b.dataset.page));
bind('enter','click',async()=>{$('enter').disabled=true;try{api.reset();await api.request('/demo/login',{method:'POST',body:{role:'owner'}});sessionStorage.removeItem('remember-web-space');localStorage.removeItem('remember-signed-out');await connect();}finally{$('enter').disabled=false;}});
bind('refresh','click',()=>refresh(true));bind('gardenMode','click',()=>{state.list=false;renderGarden();});bind('listMode','click',()=>{state.list=true;renderGarden();});bind('search','input',renderGarden);
bind('viewsMode','click',()=>{state.section='views';state.personIndex=0;renderPerson();});bind('facetsMode','click',()=>{state.section='facets';state.facet='';state.personIndex=0;renderPerson();});
for(const [id,mode] of [['evidenceMode','evidence'],['personaMode','persona']])bind(id,'click',()=>{state.mode=mode;renderChat();});
bind('questionForm','submit',ask);bind('clearChat','click',()=>{stopMedia();state.chat=[];renderChat();});bind('closeDetail','click',closeDetail);$('detail').addEventListener('close',()=>{detailTicket++;stopMedia();selection=null;});
bind('backDetail','click',()=>{stopMedia();renderCluster();$('detail').scrollTop=0;});bind('settings','click',()=>{$('help').showModal();});bind('closeHelp','click',()=>{$('help').close();});
bind('exit','click',async()=>{await api.request('/api/v1/accounts/logout',{method:'POST'});reset();$('help').close();});
addEventListener('offline',()=>{stopMedia();report('当前离线，内容无法更新。恢复连接后会重新同步。',true);});addEventListener('online',()=>refresh(true));
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopMedia();else if(Date.now()-state.updated>15000)refresh();});
addEventListener('focus',()=>{if(Date.now()-state.updated>15000)refresh();});
setInterval(()=>{if(!document.hidden&&Date.now()-state.updated>60000)refresh();},60000);
async function start(){
  try{state.config=await api.request('/web-config');if(!state.config.demo_subject_id||!state.config.demo_roles.includes('owner')){reset();$('enter').disabled=true;$('entryState').textContent='陈守义的专用体验入口尚未配置。请通过本地启动脚本连接。';return;}try{await connect();}catch(e){if(e.status===401)reset();else throw e;}}
  catch(e){reset();handle(e);}
  if('serviceWorker' in navigator&&window.isSecureContext)navigator.serviceWorker.register('/sw.js').catch(()=>{});
}
start();
