'use strict';
const $ = id => document.getElementById(id);
const state = {epoch:0,token:'', spaces:[], space:null, stories:[], grants:[], blob:null, recorder:null, caps:null,
  stream:null, context:null, urls:new Set(), uploaded:null, uploadKey:null, review:null,
  answer:null, captureQuestion:null, selectedStory:null, calibration:null, request:null, recordingMs:0, tick:0, lastTick:0};
const profileDrafts = new Map();
let authAttempt=0;
const statuses = {uploaded:'已保存，等待转写',transcribing:'正在转写原音',extracting:'正在整理',modeling:'正在关联记忆',ready:'整理完成',failed:'处理失败，原音已保留'};
const root = () => '/api/v1/workbench/subjects/' + encodeURIComponent(state.space.subject_id);
const subjectRoot = () => '/api/v1/subjects/' + encodeURIComponent(state.space.subject_id);
const owner = () => state.space?.role === 'owner';
function capturePresentation(caps){
  if(caps.stt_processing==='client')return {serverUpload:false,notice:`客户端负责转写，本服务保存原音和机器稿并等待核对 · ${caps.ai==='http'?(caps.ai_available?'云端文字服务已连接':'云端文字服务未连接'):'文字整理仍为测试配置'}。当前网页可核对已导入故事；录下的新原音请先下载，再由客户端工具转写并导入。`};
  const cloud=caps.stt_processing==='cloud';
  const route=cloud?`云端转写 ${caps.stt_model||''} · ${caps.stt_host||'地址待配置'}`:'配置的转写服务';
  return {serverUpload:true,notice:caps.live_configured?`${route} · ${caps.stt_configured?'配置已载入，实际可用性以处理结果为准':'连接配置未完成'} · ${caps.ai_available?'云端文字服务已连接':'云端文字服务未连接'}`:'当前配置含替代模型，仅可用于接口测试，不属于真实验收'};
}
function notice(message, error=false) { $('notice').hidden=false; $('notice').replaceChildren(node('span',message),button('收起',()=>{$('notice').hidden=true;})); $('notice').dataset.error=String(error); }
async function api(path, options={}) {
  const epoch=state.epoch;
  const headers = {...options.headers}; if(state.token && state.token!=='@cookie')headers.Authorization='Bearer '+state.token;
  if (options.body && !(options.body instanceof FormData)) { headers['Content-Type']='application/json'; options.body=JSON.stringify(options.body); }
  const response = await fetch(path,{...options,headers,cache:'no-store'});
  const data=await (options.audio&&response.ok?response.blob():response.json().catch(()=>({})));
  if(epoch!==state.epoch)throw new Error('身份或空间已切换，已丢弃之前的响应。');
  if(!response.ok){const e=new Error(data.error_message||'操作未完成，请重试。');e.status=response.status;throw e;}
  return data;
}
function on(id, event, action) { $(id).addEventListener(event, async e=>{try{await action(e);}catch(error){notice(error.message,true);}}); }
function node(tag,text,cls) {const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function button(text,action){const n=node('button',text);n.addEventListener('click',async()=>{n.disabled=true;try{await action();}catch(e){notice(e.message,true);}finally{n.disabled=false;}});return n;}
function objectURL(blob){const url=URL.createObjectURL(blob);state.urls.add(url);return url;}
function stopMedia(){document.querySelectorAll('audio').forEach(a=>{a.pause();a.removeAttribute('src');a.load();});for(const u of state.urls)URL.revokeObjectURL(u);state.urls.clear();}
function clearView(){stopMedia();LiveGarden.clear();$('liveGarden').replaceChildren();$('profileCandidates').replaceChildren();['stories','recent','portraitViews','answer','grants','requests','revisions','calibrations','detail'].forEach(id=>$(id).replaceChildren());$('detailDialog').close();$('reviewDialog').close();state.answer=null;}
function resetIdentityState(){state.epoch++;clearView();profileDrafts.clear();state.stories=[];state.grants=[];state.blob=null;state.uploaded=null;state.uploadKey=null;state.review=null;state.captureQuestion=null;state.calibration=null;state.request=null;refreshing=false;state.recorder=null;state.stream?.getTracks().forEach(t=>t.stop());state.stream=null;state.context?.close();state.context=null;cancelAnimationFrame(state.tick);document.querySelectorAll('input,textarea').forEach(n=>{if(n.type==='checkbox')n.checked=false;else n.value='';});$('capturePreview').hidden=true;$('saveLocal').hidden=true;$('upload').disabled=true;$('recordState').textContent='尚未录音';$('captureMode').value='normal';$('revisionTarget').hidden=true;$('suggestion').replaceChildren();}
function tab(name){document.querySelectorAll('.page').forEach(p=>p.hidden=p.id!==name);document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-current',b.dataset.tab===name?'page':'false'));}
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>tab(b.dataset.tab)));
function options(select,rows,id,label){const old=select.value;select.replaceChildren();rows.forEach(row=>{const opt=node('option',label(row));opt.value=row[id];select.append(opt);});if(rows.some(row=>row[id]===old))select.value=old;}
async function login(sessionToken){const attempt=++authAttempt;state.token=typeof sessionToken==='string'?sessionToken:$('token').value.trim();if(!state.token)throw new Error('请输入本机身份凭据。');const result=await api('/api/v1/workbench/spaces');if(attempt!==authAttempt)return;localStorage.removeItem('remember-signed-out');state.spaces=result.items;options($('space'),result.items,'subject_id',s=>s.display_name+' · '+(s.role==='owner'?'记录自己':'授权读者'));$('identity').textContent=result.display_name+' · '+result.actor_id;state.space=result.items[0]||null;$('login').hidden=true;$('workspace').hidden=false;$('logout').hidden=false;$('token').value='';if(state.space)await changeSpace();else notice('当前没有可进入的空间，请让记录者授权故事。');}
on('enter','click',login);
on('logout','click',async()=>{if(state.recorder&&state.recorder.state!=='inactive')throw new Error('请先完成并保存当前录音。');if(state.blob&&!state.uploaded&&!confirm('当前有未上传的原音。退出会丢失页面中的录音，仍然退出？'))return;++authAttempt;localStorage.setItem('remember-signed-out','1');try{await api('/api/v1/accounts/logout',{method:'POST'});}catch(e){notice('本机已退出；服务端撤销未完成，将按会话期限失效。',true);}resetIdentityState();state.token='';state.space=null;$('workspace').hidden=true;$('login').hidden=false;$('logout').hidden=true;});
on('space','change',changeSpace);
async function changeSpace(){if((state.recorder&&state.recorder.state!=='inactive')||(state.blob&&!state.uploaded)){$('space').value=state.space.subject_id;throw new Error('请先完成并保存当前录音，再切换空间。');}resetIdentityState();state.space=state.spaces.find(s=>s.subject_id===$('space').value);$('title').textContent=state.space.display_name+'的记忆';$('capture').hidden=!owner();$('grantForm').hidden=!owner();$('vocabularyPanel').hidden=!owner();if(owner())$('vocabulary').value=(await api(root()+'/vocabulary')).text;$('captureContext').textContent=owner()?'先保存原音，再核对文字。未经确认，不会发送给云端整理。':'这里只能查看获授权的故事。你可以提问，也可以邀请本人补充。';await refresh();}
let refreshing=false;
async function refresh(){if(!state.token||!state.space||refreshing)return;refreshing=true;try{
  const [data, grants, portrait, requests, caps]=await Promise.all([api(root()+'/stories'),api(root()+'/grants'),api(root()+'/portrait'),api(root()+'/requests'),api('/api/v1/workbench/capabilities')]);
  state.stories=data.items;state.grants=grants.items;
  if(state.selectedStory&&!state.stories.some(s=>s.episode_id===state.selectedStory&&!s.unavailable)){stopMedia();$('detailDialog').close();$('detail').replaceChildren();state.selectedStory=null;}
  if(state.caps?.cloud_asr_policy!==caps.cloud_asr_policy)$('ownSpeech').checked=false;
  state.caps=caps;
  const cloud=caps.stt_processing==='cloud';
  const presentation=capturePresentation(caps);
  $('ownSpeech').disabled=!presentation.serverUpload||(cloud&&!caps.stt_configured);
  if(!presentation.serverUpload)$('upload').disabled=true;
  $('capabilities').textContent=presentation.notice;
  $('asrConsentText').textContent=!presentation.serverUpload?'客户端导入后，请到故事页核对机器稿；本页不向ASR发送原音。':cloud?`这是我本人的讲述，我同意保存原音，并将本段完整音频发送到 ${caps.stt_host||'待配置的服务'}（${caps.stt_model}）转写。核对后才整理记忆。`:'这是我本人的讲述，我同意保存原音并交给配置的转写服务。';
  if(cloud&&caps.stt_model==='paraformer-v2')$('asrConsentText').textContent+=' 百炼使用私有临时音频副本，有效期48小时；不需要电脑接力。';
  renderStories();renderGrants();renderRequests(requests.items);renderPortrait(portrait);LiveGarden.render($('liveGarden'),state.stories,openStory);$('profilePanel').hidden=!owner();if(owner())await renderProfiles(await api(root()+'/profile-candidates'));
  options($('grantEpisode'),state.stories.filter(s=>s.status==='ready'&&s.reviewed),'episode_id',s=>storyTitle(s));
  const memories=state.stories.flatMap(s=>s.memories).filter(m=>m.review_state==='active');options($('targetMemory'),memories,'memory_item_id',m=>m.content.slice(0,70));
  if(owner() && state.stories.length) {const [revisions, prompts, calibrations]=await Promise.all([api(root()+'/revisions'),api(subjectRoot()+'/questions'),api(subjectRoot()+'/calibrations')]);renderRevisions(revisions.items);renderSuggestion(prompts.items[0]);renderCalibrations(calibrations.items);}
  if(state.answer){const latest=await api(subjectRoot()+'/twin/answers/'+state.answer.answer_id);if(latest.stale){$('answer').replaceChildren(node('p','相关记忆或授权已变化，请重新提问。'));state.answer=null;stopMedia();}}
}catch(e){if(e.status===404||e.status===401){clearView();state.stories=[];state.grants=[];}notice(e.message,true);}finally{refreshing=false;}}
setInterval(()=>{if(!document.hidden&&!$('reviewDialog').open&&!$('profilePanel').contains(document.activeElement))refresh();},5000);
function storyTitle(s){return s.unavailable?'相关故事已更新':s.memories.find(m=>m.review_state==='active')?.content.slice(0,48)||s.transcript?.slice(0,48)||'一段尚待整理的讲述';}
function storyCard(story){const card=node('article',undefined,'story');card.append(node('h3',storyTitle(story)),node('small',new Date(story.recorded_at).toLocaleString('zh-CN')+' · '+(story.waiting_for_review?'待核对文字':statuses[story.status]||story.status)));if(story.error_message)card.append(node('p',story.error_code?.startsWith('AI')?'记忆整理服务暂不可用。原音与核对文字已保留，请稍后重试。':'转写处理未完成，原音已保留。请检查服务后重试。','danger'));const actions=node('div',undefined,'actions');if(!story.unavailable){actions.append(button('打开故事',()=>openStory(story)));if(owner()&&!story.reviewed)actions.append(button('核对转写',()=>review(story.episode_id)));if(owner()&&story.status==='failed')actions.append(button('重试处理',async()=>{await api('/api/v1/episodes/'+story.episode_id+'/retry',{method:'POST'});await refresh();}));if(owner()&&story.can_reextract_empty)actions.append(button('未提取到记忆，重新整理',async()=>{await api('/api/v1/episodes/'+story.episode_id+'/reextract-empty',{method:'POST'});await refresh();}));}card.append(actions);return card;}
function renderStories(){const q=$('search').value.trim();const rows=state.stories.filter(s=>!q||[s.transcript,...s.memories.map(m=>m.content)].some(t=>t?.includes(q)));$('stories').replaceChildren(...rows.map(storyCard));$('recent').replaceChildren(...state.stories.slice(0,3).map(storyCard));if(!rows.length)$('stories').append(node('p','这里还没有符合条件的故事。'));if(!state.stories.length)$('recent').append(node('p','还没有故事。录一段你愿意留下的话，或等待本人分享。'));}
on('search','input',renderStories);
async function playInto(container,episode){stopMedia();const blob=await api(root()+'/stories/'+episode+'/audio',{audio:true});const audio=node('audio');audio.controls=true;audio.src=objectURL(blob);audio.setAttribute('aria-label','来源故事的完整原音');container.append(audio);await audio.play().catch(()=>{});}
async function openStory(story){state.selectedStory=story.episode_id;const box=$('detail');box.replaceChildren(node('h2',storyTitle(story)),node('p','完整原音与转写；未做音频逐字对齐。'));box.append(button('播放完整原音',()=>playInto(box,story.episode_id)));box.append(node('h3',story.waiting_for_review?'机器转写 · 尚未核对':'核对文字'),node('p',story.transcript||'转写尚未完成。','quote'));if(owner()&&story.machine_transcript){const d=node('details');d.append(node('summary','机器原始转写'),node('p',story.machine_transcript));box.append(d);}for(const memory of story.memories){const m=node('div',undefined,'memory');m.append(node('p',memory.content),node('small',memory.review_state==='superseded'?'已被本人纠正，保留历史':memory.review_state==='pending'?'修订候选，尚未用于回答':memory.origin==='owner_supplement'?'本人书面补充 · 不属于录音原话':'系统整理 · '+memory.source_type));for(const e of memory.evidence)m.append(node('p',e.excerpt||''));if(owner()&&memory.review_state==='active'){m.append(button('补充或纠正',()=>{$('detailDialog').close();$('targetMemory').value=memory.memory_item_id;$('captureMode').value='supplement';$('revisionTarget').hidden=false;tab('today');}),button('删除这条记忆',async()=>{if(!confirm('删除这条记忆并更新相关回答？原音和核对文字保留。'))return;await api(subjectRoot()+'/memories/'+memory.memory_item_id,{method:'DELETE'});$('detailDialog').close();await refresh();}));}box.append(m);}box.append(node('small','转写：'+(story.stt_model_version||'未完成')+' · 整理：'+(story.model_version||'未完成')));$('detailDialog').showModal();}
async function review(id){const data=await api('/api/v1/episodes/'+id+'/transcript-review');if(data.state!=='reviewing')throw new Error(data.state==='submitted'?'已经确认。':'转写尚未完成；可以继续播放原音或稍后重试。');state.review=id;$('reviewText').value=data.transcript;$('reviewSupplement').value=data.supplement||'';$('reviewDialog').showModal();}
on('confirmReview','click',async()=>{const text=$('reviewText').value.trim();if(!text)throw new Error('核对文字不能为空。');await api('/api/v1/episodes/'+state.review+'/transcript-review',{method:'PATCH',body:{transcript:text,supplement:$('reviewSupplement').value.trim()}});$('reviewDialog').close();notice('文字已确认，正在整理。原音和机器转写均保留。');await refresh();});
on('captureMode','change',()=>{$('revisionTarget').hidden=$('captureMode').value==='normal';});
function prepareBlob(blob){state.blob=blob;state.uploaded=null;state.uploadKey=crypto.randomUUID();$('ownSpeech').checked=false;$('capturePreview').src=objectURL(blob);$('capturePreview').hidden=false;$('upload').disabled=false;$('saveLocal').hidden=false;notice('原音已留在当前页面，请保存到本机服务；失败时仍可下载。');}
on('audioFile','change',()=>{const file=$('audioFile').files[0];if(file)prepareBlob(file);});
on('saveLocal','click',()=>{if(!state.blob)return;const a=node('a');a.href=objectURL(state.blob);a.download='勿忘我-原音.'+(state.blob.type.includes('mp4')?'m4a':'webm');a.click();});
on('record','click',async()=>{stopMedia();if(!navigator.mediaDevices?.getUserMedia)throw new Error('这个浏览器不支持录音，请导入音频。');const recordingEpoch=state.epoch;const stream=await navigator.mediaDevices.getUserMedia({audio:true});if(recordingEpoch!==state.epoch){stream.getTracks().forEach(t=>t.stop());throw new Error('身份已变化，已取消录音。');}state.stream=stream;try{
  const types=['audio/webm;codecs=opus','audio/mp4'];const mimeType=types.find(t=>MediaRecorder.isTypeSupported(t));const rec=new MediaRecorder(stream,mimeType?{mimeType}:{});state.recorder=rec;const chunks=[];rec.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};rec.onstop=()=>{if(recordingEpoch!==state.epoch){stream.getTracks().forEach(t=>t.stop());return;}prepareBlob(new Blob(chunks,{type:rec.mimeType}));stream.getTracks().forEach(t=>t.stop());state.context?.close();state.context=null;cancelAnimationFrame(state.tick);$('volume').value=0;$('record').hidden=false;$('pause').hidden=true;$('finish').hidden=true;$('recordState').textContent='录音已完成，等待保存';};
  state.context=new AudioContext();const analyser=state.context.createAnalyser();analyser.fftSize=256;state.context.createMediaStreamSource(stream).connect(analyser);const samples=new Uint8Array(analyser.fftSize);state.recordingMs=0;state.lastTick=performance.now();
  function meter(now){const running=rec.state==='recording';if(running)state.recordingMs+=now-state.lastTick;state.lastTick=now;analyser.getByteTimeDomainData(samples);$('volume').value=running?Math.sqrt(samples.reduce((a,x)=>a+((x-128)/128)**2,0)/samples.length):0;$('recordState').textContent=(running?'正在录音':'已暂停')+' · '+Math.floor(state.recordingMs/60000)+':'+String(Math.floor(state.recordingMs/1000)%60).padStart(2,'0');state.tick=requestAnimationFrame(meter);}
  rec.start(1000);state.tick=requestAnimationFrame(meter);$('record').hidden=true;$('pause').hidden=false;$('pause').textContent='暂停';$('finish').hidden=false;
}catch(e){stream.getTracks().forEach(t=>t.stop());throw e;}});
on('pause','click',()=>{const r=state.recorder;if(r.state==='recording'){r.pause();$('pause').textContent='继续';}else{r.resume();$('pause').textContent='暂停';}});
on('finish','click',()=>state.recorder.stop());
window.addEventListener('beforeunload',e=>{if(state.recorder?.state==='recording'||state.recorder?.state==='paused'||(state.blob&&!state.uploaded)){e.preventDefault();e.returnValue='';}});
document.addEventListener('visibilitychange',()=>{if(document.hidden&&state.recorder&&state.recorder.state!=='inactive'){state.recorder.stop();notice('已结束录音并保留在页面中，返回后请保存。');}});
async function consent(scope){const data=await api('/api/v1/consents?subject_id='+encodeURIComponent(state.space.subject_id));const found=data.find(c=>c.scope===scope&&c.status==='granted');return found?.consent_id||(await api('/api/v1/consents',{method:'POST',body:{subject_id:state.space.subject_id,scope}})).consent_id;}
on('upload','click',async()=>{if(!owner()||!state.blob)throw new Error('请先录音或导入。');if(!state.caps)throw new Error('请先刷新服务配置。');const captureCaps=state.caps;if(captureCaps.stt_processing==='client')throw new Error('请先下载原音，由客户端工具完成转写并导入，再到故事页核对。');if(captureCaps.stt_processing==='cloud'&&!captureCaps.stt_configured)throw new Error('云端转写配置尚未完成，请先下载保留原音。');if(!$('ownSpeech').checked)throw new Error('请确认这是本人讲述，并同意本段原音的转写方式。');$('upload').disabled=true;try{
  const mode=$('captureMode').value,target=$('targetMemory').value,time=$('timeText').value.trim();if(mode!=='normal'&&!target)throw new Error('请选择旧记忆。');if(mode==='change'&&!time)throw new Error('请填写变化的大致时间。');
  if(!state.uploaded){const data=new FormData();data.set('subject_id',state.space.subject_id);data.set('recording_consent_id',await consent('RECORDING'));data.set('idempotency_key',state.uploadKey);data.set('source','IMPORT');data.set('recorded_at',new Date().toISOString());data.set('audio_ref','workbench-recording');const metadata={capture_client:'local-web-workbench'};if(captureCaps.stt_processing==='cloud')metadata.cloud_asr_policy=captureCaps.cloud_asr_policy;if(state.captureQuestion)metadata.question_id=state.captureQuestion.question_id;if(state.calibration)metadata.calibration_id=state.calibration.calibration_id;data.set('metadata',JSON.stringify(metadata));data.set('file',state.blob,'recording.'+(state.blob.type.includes('mp4')?'m4a':'webm'));state.uploaded=(await api('/api/v1/episodes',{method:'POST',body:data})).episode_id;}
  if(mode!=='normal')await api(root()+'/revisions',{method:'POST',body:{episode_id:state.uploaded,target_memory_id:target,kind:mode,time_text:time||null}});
  state.calibration=null;state.captureQuestion=null;notice('录音已保存在本机服务。正在等待转写服务；云端整理需要你再确认。');await refresh();tab('archive');
}finally{$('upload').disabled=false;}});
async function cloudConsent(){if(owner())return consent('CLOUD_TWIN');const grant=state.grants.find(g=>g.cloud_processing_allowed);if(!grant)throw new Error('本人尚未允许将共享故事用于云端问答。');return grant.grant_id;}
on('ask','click',async()=>{if(!$('cloudAsk').checked)throw new Error('请先确认云端文字处理。');const question=$('question').value.trim();if(!question)throw new Error('请写下问题。');$('ask').disabled=true;try{const result=await api(subjectRoot()+'/twin/answers',{method:'POST',body:{question,cloud_consent_id:await cloudConsent()}});state.answer=result;renderAnswer(result);}finally{$('ask').disabled=false;}});
function renderAnswer(result){const box=$('answer');box.replaceChildren(node('h3',{ORIGINAL:'本人原话 · 核对文字',SIMULATION:'依据记录生成 · 不是本人原话',UNKNOWN:'目前的记录还不足以回答'}[result.response_type]),node('p',result.answer,'quote'));for(const source of result.evidence){const m=node('div',undefined,'memory');m.append(node('p',source.excerpt),node('small',source.source_type==='CALIBRATION'?'本人补充或修订，原音仅供关联参考':'来自核对后的讲述'),button('播放来源原音',()=>playInto(m,source.episode_id)));box.append(m);}box.append(node('small','模型：'+result.model_version+' · 资料版本：'+result.person_model_version));if(owner()&&result.response_type!=='UNKNOWN')box.append(button('用本人回答进行校准',async()=>{state.calibration=await api(subjectRoot()+'/calibrations',{method:'POST',body:{twin_answer_id:result.answer_id,cloud_consent_id:await cloudConsent()}});$('captureMode').value='normal';$('revisionTarget').hidden=true;tab('today');notice('Twin 回答已锁定。请新录一段本人回答：'+result.question);}));}
on('requestQuestion','click',async()=>{const text=$('question').value.trim();if(!text)throw new Error('请先写下希望补充的问题。');await api(root()+'/requests',{method:'POST',body:{text}});notice('问题已交给本人决定是否回答，没有写入记忆。');await refresh();});
function renderGrants(){const box=$('grants');box.replaceChildren();for(const g of state.grants){const row=node('div',undefined,'story');row.append(node('p',storyTitle(state.stories.find(s=>s.episode_id===g.episode_id)||{memories:[]})+' → '+g.reader_actor_id),node('small',g.cloud_processing_allowed?'已允许云端问答':'仅查看故事和原音'));if(owner())row.append(button('撤销授权',async()=>{if(!confirm('撤销后将阻止后续访问，但无法收回对方已看到或保存的内容。'))return;await api(root()+'/grants/'+g.grant_id,{method:'DELETE'});await refresh();}));box.append(row);}}
on('grant','click',async()=>{if(!$('shareAudio').checked)throw new Error('请明确确认分享完整原音和文字。');await api(root()+'/grants',{method:'POST',body:{episode_id:$('grantEpisode').value,reader_actor_id:$('readerId').value.trim(),include_audio_confirmed:true,cloud_processing_allowed:$('shareCloud').checked}});notice('已授权选定故事。其他故事仍保持私密。');await refresh();});
function renderRequests(items){const box=$('requests');box.replaceChildren();for(const r of items){const row=node('article',undefined,'story');row.append(node('p',r.text),node('small',({pending:'待回答',snoozed:'稍后处理',declined:'已婉拒',answered:'本人已回答'})[r.status]));if(owner()&&r.status!=='answered'){row.append(button('录音回答',()=>{state.request=r;state.calibration=null;tab('today');notice('请录制回答，完成核对后在这里关联故事；分享需要另行授权。');}),button('稍后',async()=>{await api(root()+'/requests/'+r.request_id,{method:'PATCH',body:{status:'snoozed'}});await refresh();}),button('婉拒',async()=>{await api(root()+'/requests/'+r.request_id,{method:'PATCH',body:{status:'declined'}});await refresh();}));const select=node('select');select.setAttribute('aria-label','选择回答录音');options(select,state.stories.filter(s=>s.reviewed&&s.status==='ready'),'episode_id',storyTitle);row.append(select,button('关联已核对回答',async()=>{await api(root()+'/requests/'+r.request_id,{method:'PATCH',body:{status:'answered',answer_episode_id:select.value}});notice('已关联回答；没有自动授权给读者。');await refresh();}));}if(r.answer_episode_id){row.append(button('打开已分享的回答',()=>{const s=state.stories.find(x=>x.episode_id===r.answer_episode_id);if(s)return openStory(s);throw new Error('这段回答尚未分享。');}));}box.append(row);}}
function renderRevisions(items){const box=$('revisions');box.replaceChildren();for(const r of items){const row=node('article',undefined,'story');const old=state.stories.flatMap(s=>s.memories).find(m=>m.memory_item_id===r.target_memory_id);const next=state.stories.find(s=>s.episode_id===r.episode_id);row.append(node('h3',({supplement:'补充',correction:'纠正',change:'情况变化'})[r.kind]+' · '+(r.status==='confirmed'?'已确认':'等待本人核对')),node('p','原记忆：'+(old?.content||'原记忆已变化')),node('p','新记忆：'+(next?.memories.map(m=>m.content).join('；')||'尚待整理')));if(r.time_text)row.append(node('p','发生时间：'+r.time_text));if(r.status==='pending')row.append(button('确认上述关系',async()=>{if(!confirm('确认这段新录音与旧记忆的关系？纠正会让旧说法退出当前回答，原音继续保留。'))return;await api(root()+'/revisions/'+r.revision_id+'/confirm',{method:'POST'});await refresh();}));box.append(row);}}
function renderPortrait(data){const box=$('portraitViews');box.className='portrait-grid';box.replaceChildren();for(const [title,items] of Object.entries(data.views)){const section=node('section');section.append(node('h2',title));if(!items.length)section.append(node('p','这里还没有足够的可见材料。','muted'));for(const item of items){const row=node('div',undefined,'memory');row.append(node('p',item.content),node('small',item.label),button('回到来源',()=>openStory(state.stories.find(s=>s.episode_id===item.episode_id))));section.append(row);}box.append(section);}}
function renderSuggestion(q){const box=$('suggestion');box.replaceChildren();if(!owner()||!q)return;box.append(node('h2','如果愿意，再聊一点'),node('p',q.text),button('就聊这个问题',()=>{state.captureQuestion=q;state.calibration=null;$('captureContext').textContent=q.text+'（可以随时停止，无需回答所有问题）';tab('today');}),button('结束引导',()=>{state.captureQuestion=null;$('captureContext').textContent='可以自由讲述，不必回答建议问题。';}),button('稍后再聊',async()=>{await api(root()+'/questions/'+q.question_id,{method:'PATCH',body:{status:'snoozed'}});await refresh();}),button('跳过这个问题',async()=>{await api(root()+'/questions/'+q.question_id,{method:'PATCH',body:{status:'declined'}});await refresh();}));}
function renderCalibrations(items){const box=$('calibrations');box.replaceChildren();for(const r of items){const row=node('article',undefined,'story');row.append(node('h3',r.question),node('p',r.status==='complete'?r.summary:r.status==='stale'?'来源已变化，这次校准已失效':'Twin 回答已锁定，等待本人回答'));if(r.status==='awaiting_human'&&r.human_episode_id)row.append(button('比较两份回答',async()=>{if(!confirm('将已确认的本人回答与锁定的 Twin 回答发送给云端进行比较？'))return;await api(subjectRoot()+'/calibrations/'+r.calibration_id+'/complete',{method:'POST',body:{cloud_consent_id:await cloudConsent()}});await refresh();}));for(const d of r.dimensions||[])row.append(node('p',JSON.stringify(d)));box.append(row);}}

async function renderProfiles(data){
  const box=$('profileCandidates');box.replaceChildren();
  const labels={pending:'等待本人确认',confirmed:'本人已确认',rejected:'本人已拒绝',stale:'依据已变化',superseded:'历史理解',applied:'已用于更新',conflicted:'存在冲突，等待核对'};
  const actions={ADD:'新增理解',SUPPORT:'支持已有理解',CONFLICT:'与已有理解冲突',CHANGE:'理解随时间变化'};
  for(const j of data.jobs){const kind=j.kind==='relations'?'关系建议':'人物归纳';box.append(node('p',kind+'：'+(j.status==='failed'?(j.error||'失败，可明确重试'):j.status==='running'?'正在分析有效资料…':j.status==='complete'?'已完成，请核对结果':'任务已排队')));}
  for(const item of data.items){
    const article=node('article',undefined,'story');article.append(node('h3',item.statement),node('p',item.context),node('small',item.label+' · '+(labels[item.status]||item.status)));
    for(const id of [...item.evidence_ids,...item.counter_evidence_ids]){
      const source=item.evidence?.find(e=>e.evidence_id===id);
      const story=state.stories.find(s=>s.episode_id===source?.episode_id||s.memories.some(m=>m.evidence.some(e=>e.evidence_id===id)));
      article.append(node('blockquote',source?.excerpt||'原文片段：'+id));
      if(story)article.append(button('查看'+(item.counter_evidence_ids.includes(id)?'反例':'支持')+'来源',()=>openStory(story)));
    }
    if(item.status==='pending'){
      const action=node('select');action.setAttribute('aria-label','如何使用这条理解');
      for(const [value,label] of Object.entries(actions)){const option=node('option',label);option.value=value;action.append(option);}
      const target=node('select');target.setAttribute('aria-label','关联的已有理解');
      const empty=node('option','请选择旧理解并核对情境');empty.value='';target.append(empty);
      for(const old of data.items.filter(o=>o.candidate_id!==item.candidate_id&&(o.stored_status||o.status)==='confirmed'&&o.domain===item.domain&&o.kind===item.kind)){
        const option=node('option',old.statement+' · '+old.context+(old.status==='stale'?'（需重新核对依据）':''));option.value=old.candidate_id;target.append(option);
      }
      const reason=node('textarea');reason.placeholder='为什么这样关联？请核对两条理解的含义和情境。';reason.setAttribute('aria-label','更新理由');reason.maxLength=1000;
      const time=node('input');time.placeholder='变化时间，例如：退休以后（不必猜具体日期）';time.setAttribute('aria-label','变化时间');time.maxLength=200;
      const draft=profileDrafts.get(item.candidate_id);if(draft){action.value=draft.action;target.value=draft.target;reason.value=draft.reason;time.value=draft.time;}
      const rememberDraft=()=>profileDrafts.set(item.candidate_id,{action:action.value,target:target.value,reason:reason.value,time:time.value});
      for(const input of [action,target,reason,time]){input.addEventListener('input',rememberDraft);input.addEventListener('change',rememberDraft);}
      const sync=()=>{target.hidden=action.value==='ADD';time.hidden=action.value!=='CHANGE';};action.addEventListener('change',sync);sync();
      article.append(action,target,reason,time,button('保存为待确认更新',async()=>{
        await api(root()+'/profile-candidates/updates',{method:'POST',body:{candidate_id:item.candidate_id,action:action.value,target_candidate_id:action.value==='ADD'?null:target.value,reason:reason.value,time_text:action.value==='CHANGE'?time.value:''}});profileDrafts.delete(item.candidate_id);await refresh();
      }),button('不符合我的意思',async()=>{await api(root()+'/profile-candidates/'+item.candidate_id+'/reject',{method:'POST'});await refresh();}));
    }else if(item.status==='confirmed')article.append(button('撤回这项确认',async()=>{await api(root()+'/profile-candidates/'+item.candidate_id+'/reject',{method:'POST'});await refresh();}));
    box.append(article);
  }
  if(!data.items.length)box.append(node('p','还没有人物候选。生成和确认是两个独立步骤。','muted'));
  const updates=await api(root()+'/profile-candidates/updates');
  for(const update of updates.items){
    const article=node('article',undefined,'story');const next=data.items.find(i=>i.candidate_id===update.candidate_id);const old=data.items.find(i=>i.candidate_id===update.target_candidate_id);
    article.append(node('h3',(actions[update.action]||update.action)+' · '+(labels[update.status]||update.status)),node('p','新观察：'+(next?.statement||update.candidate_id)));
    if(old)article.append(node('p','已有理解：'+old.statement+'；情境：'+old.context));
    article.append(node('p',update.reason));if(update.time_text)article.append(node('p','时间：'+update.time_text));
    if(update.origin==='model'){
      article.append(node('small','系统建议 · '+update.model_version+' · '+update.prompt_version));
      for(const id of update.suggestion_evidence_ids||[]){const source=[...(next?.evidence||[]),...(old?.evidence||[])].find(e=>e.evidence_id===id);if(source)article.append(node('blockquote',source.excerpt));}
    }
    if(update.question)article.append(node('p',update.question));
    if(update.status==='pending')article.append(button('确认上述更新',async()=>{if(!confirm('已核对双方原文与情境？支持或变化会保留历史版本；冲突会暂停使用这两条理解。'))return;await api(root()+'/profile-candidates/updates/'+update.update_id+'/confirm',{method:'POST'});await refresh();}),button('拒绝这次更新',async()=>{await api(root()+'/profile-candidates/updates/'+update.update_id+'/reject',{method:'POST'});await refresh();}));
    box.append(article);
  }
}
on('refreshProfile','click',async()=>{if(!confirm('将当前有效的核对文字交给云端模型提出人物理解候选？归纳不会自动成为事实。'))return;await api(root()+'/profile-candidates/refresh',{method:'POST',body:{cloud_consent_id:await cloudConsent()}});await refresh();});
on('suggestRelations','click',async()=>{if(!confirm('将候选、已有理解与相关原文交给云端比较？结果只作为待确认建议，不会自动修改事实。'))return;await api(root()+'/profile-candidates/suggest-relations',{method:'POST',body:{cloud_consent_id:await cloudConsent()}});await refresh();});

let registering=false;
on('switchRegister','click',()=>{registering=!registering;$('nameField').hidden=!registering;$('accountEnter').textContent=registering?'创建我的空间':'登录';$('switchRegister').textContent=registering?'已有账号，返回登录':'第一次使用，创建账号';});
on('accountEnter','click',async()=>{++authAttempt;const body={username:$('username').value.trim(),password:$('password').value};if(registering)body.display_name=$('displayName').value.trim();$('accountEnter').disabled=true;try{await api('/api/v1/accounts/'+(registering?'register':'login'),{method:'POST',body});$('password').value='';await login('@cookie');}finally{$('accountEnter').disabled=false;}});
on('saveVocabulary','click',async()=>{await api(root()+'/vocabulary',{method:'PUT',body:{text:$('vocabulary').value}});notice('用词已保存；没有自动发送给模型或读者。');});
on('useVocabulary','click',async()=>{const data=await api(root()+'/vocabulary');const combined=[$('reviewSupplement').value,data.text].filter(Boolean).join('\n');if(combined.length>3000)throw new Error('补充超过3000字，请选择本次需要的词语。');$('reviewSupplement').value=combined;});
(async()=>{if(localStorage.getItem('remember-signed-out')==='1')return;const attempt=authAttempt+1;try{await login('@cookie');}catch(e){if(authAttempt===attempt)state.token='';}})();
