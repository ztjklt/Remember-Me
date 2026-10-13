'use strict';
// Browser HTTP fixtures exercise client behavior; no provider quality claim.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const playwright=require('playwright');
const assets=path.join(__dirname,'../app/workbench');
async function run(){
 const browser=await playwright.chromium.launch({headless:true,channel:'chrome'});let passed=0;
 try{for(const owner of [true,false]){
  const page=await browser.newPage({viewport:{width:412,height:915}}),calls=[],errors=[];let revoked=false,style=true,voiceReady=true;
  const actor=owner?'owner':'friend',notes=[],letters=[];let audio=null,answer=null;
  page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  await page.route('http://localhost:9899/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname,method=req.method();
   if(p.startsWith('/workbench/')){const file=p.split('/').pop();return route.fulfill({contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(path.join(assets,file))});}
   const raw=req.postData()||'',body=req.headers()['content-type']?.includes('application/json')?JSON.parse(raw):null;calls.push({p,method,body,raw});let data={},status=200;
   if(p==='/api/v1/workbench/spaces')data={actor_id:actor,display_name:owner?'本人':'亲友',items:[{subject_id:'a',display_name:'人物空间（虚构）',role:owner?'owner':'companion'}]};
   else if(p==='/api/v1/companion/spaces')data={items:[]};
   else if(p.endsWith('/companion'))data={role:owner?'owner':'companion',contribution_grants:owner?[]:[{actor_id:'friend',enabled:true,revision:1}],contributions:notes,letters,snapshots:[]};
   else if(p.endsWith('/narrative/style')){style=body.enabled;data={enabled:style,revision:2};}
   else if(p.endsWith('/narrative'))data={style:{enabled:style,revision:1},views:[{title:'人生足迹',records:['story']}],facets:[],records:[{id:'story',kind:'story',title:'修理收音机',text:'先找原因',status:'confirmed',source_valid:true,evidence:[]}],understandings:[{candidate_id:'understanding',status:'confirmed',statement:'遇事先查原因',context:'修理东西时',evidence:[]}]};
   else if(p.endsWith('/recipients'))data={items:[{actor_id:'friend',display_name:'亲友',username:'friend'}]};
   else if(p.includes('/voice/recipients/'))data={actor_id:'friend',enabled:method==='PUT'?body.enabled:false,revision:1};
   else if(p.endsWith('/voice/profile'))data={ready:voiceReady,can_synthesize:!revoked&&voiceReady,synthetic_presets:[],can_enroll:owner,voice_consent_id:owner?'voice-consent':null};
   else if(p==='/api/v1/consents/voice-consent/revoke'){voiceReady=false;data={status:'revoked'};}
   else if(p.endsWith('/grants'))data={items:[{grant_id:'cloud-grant',cloud_processing_allowed:1}]};
   else if(p==='/api/v1/consents')data=[{scope:'CLOUD_TWIN',status:'granted',consent_id:'cloud'}];
   else if(p.endsWith('/twin/answers')&&method==='POST')data=answer={answer_id:'answer-new',mode:body.mode,response_type:'SIMULATION',answer:'先看看哪里出了问题。',understanding_ids:['understanding'],contribution_ids:[],evidence:[]};
   else if(p.endsWith('/twin/answers/answer-new')){data=answer;if(revoked){status=404;data={error_message:'失效'};}}
   else if(p.endsWith('/speech'))data={asset_id:'saved-speech',status:'ready'};
   else if(p.endsWith('/voice/assets/saved-speech/audio')||p.endsWith('/audio/audio-one/content'))return route.fulfill({contentType:'audio/wav',body:Buffer.alloc(44)});
   else if(p.endsWith('/companion/audio')&&method==='POST')data=audio={audio_id:'audio-one',purpose:raw.includes('contribution')?'contribution':'letter',status:'saved',revision:1,transcript_text:'',reviewed_text:'',cloud_asr_policy:'policy-fixture'};
   else if(p.endsWith('/audio/audio-one/transcribe'))data=audio={...audio,status:'reviewing',revision:2,transcript_text:'机器原稿'};
   else if(p.endsWith('/audio/audio-one/review'))data=audio={...audio,status:'confirmed',revision:3,reviewed_text:body.text};
   else if(p.endsWith('/audio/audio-one'))data=audio;
   else if(p.endsWith('/contributions')&&method==='POST'){notes.push({id:'note-one',...body,author_actor_id:'friend',author_display_name:'亲友',status:'pending',revision:1,model_use_author_allowed:false,model_use_owner_allowed:false});data=notes[0];}
   else if(p.endsWith('/contributions/note-one/model-use')){notes[0].model_use_author_allowed=body.allowed;notes[0].revision++;data=notes[0];}
   else if(p.endsWith('/letters')&&method==='POST'){letters.push({id:'letter-one',...body,status:'draft',revision:1});data=letters[0];}
   else if(p.endsWith('/letters/letter-one/publish')){letters[0].status='published';letters[0].revision++;data=letters[0];}
   await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
  });
  await page.goto('http://localhost:9899/workbench/companion.html');await page.locator('#understandings h3').first().waitFor();
  assert(await page.locator('#understandings').evaluate(n=>Boolean(n.compareDocumentPosition(document.getElementById('records'))&Node.DOCUMENT_POSITION_FOLLOWING)));passed++;
  const text=await page.locator('body').innerText();assert(!/技术复核|样例技术|资料版本|版本 ID/.test(text));passed++;
  await page.locator('[data-section=dialogue]').click();await page.locator('#questionMode').selectOption('persona');await page.locator('#questionText').fill('东西坏了怎么办？');await page.locator('#questionCloud').check();await page.locator('#questionForm button[type=submit]').click();await page.getByText('先看看哪里出了问题。',{exact:true}).waitFor();assert.equal(calls.find(c=>c.p.endsWith('/twin/answers')&&c.method==='POST').body.mode,'persona');passed++;
  await page.getByRole('button',{name:'听这条回答',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#answer audio'));assert(calls.some(c=>c.p.endsWith('/twin/answers/answer-new/speech')&&c.method==='POST'&&!c.body));assert(calls.some(c=>c.p.endsWith('/voice/assets/saved-speech/audio')));passed++;
  revoked=true;await page.locator('#refresh').click();await page.waitForFunction(()=>!document.querySelector('#answer audio')&&!document.getElementById('answer').textContent);revoked=false;passed++;
  if(owner){await page.getByRole('button',{name:'允许亲友收听分身回答'}).click();await page.waitForTimeout(100);const grant=calls.find(c=>c.p.endsWith('/voice/recipients/friend')&&c.method==='PUT');assert.deepEqual(grant.body,{enabled:true});passed++;await page.getByRole('button',{name:'停用分身声音',exact:true}).click();await page.getByText('分身声音尚未启用',{exact:true}).waitFor();assert(calls.some(c=>c.p==='/api/v1/consents/voice-consent/revoke'&&c.method==='POST'));passed++;}
  const purpose=owner?'letter':'contribution',form=owner?'letterForm':'noteForm';await page.locator(`[data-section=${owner?'foryou':'family'}]`).click();
  await page.locator(`#${purpose}Audio input[type=file]`).setInputFiles({name:'own-audio.wav',mimeType:'audio/wav',buffer:Buffer.from('fixture dedicated audio')});await page.getByRole('button',{name:'上传这段声音',exact:true}).click();await page.locator(`#${purpose}Audio input[type=checkbox]`).waitFor();
  const upload=calls.find(c=>c.p.endsWith('/companion/audio')&&c.method==='POST');assert(upload.raw.includes('name="purpose"'));assert(upload.raw.includes(purpose));assert(upload.raw.includes('name="idempotency_key"'));assert(!upload.raw.includes('episode_id'));passed++;
  await page.locator(`#${purpose}Audio input[type=checkbox]`).check();await page.getByRole('button',{name:'转为文字',exact:true}).click();await page.locator(`#${purpose}Audio textarea`).waitFor();await page.locator(`#${purpose}Audio textarea`).fill('听过声音后的核对稿');await page.getByRole('button',{name:'确认文字并填入正文',exact:true}).click();await page.waitForFunction(id=>document.getElementById(id).value==='听过声音后的核对稿',owner?'letterText':'noteText');assert.equal(calls.find(c=>c.p.endsWith('/transcribe')).body.cloud_asr_policy,'policy-fixture');assert.equal(calls.find(c=>c.p.endsWith('/review')).body.revision,2);passed++;
  if(owner){await page.locator('#letterRecipient select').selectOption('friend');await page.locator('#letterTitle').fill('给你的话');}else {await page.getByText('关联一段故事（可选）',{exact:true}).click();await page.locator('#noteLinks input').check();}
  await page.locator(`#${form} button[type=submit]`).click();await page.waitForFunction(id=>document.getElementById(id).textContent.includes('听过声音后的核对稿'),owner?'letters':'notes');const sent=calls.find(c=>c.p.endsWith(owner?'/letters':'/contributions')&&c.method==='POST');assert.equal(sent.body.audio_id,'audio-one');assert.equal(sent.body.model_use_author_allowed,undefined);if(!owner)assert.deepEqual(sent.body.narrative_ids,['story']);passed++;
  if(owner){assert.equal(letters[0].status,'draft');assert(!calls.some(c=>c.p.endsWith('/publish')));await page.getByRole('button',{name:'核对收信账号后发送'}).click();await page.waitForFunction(()=>document.getElementById('letters').textContent.includes('已发送'));assert.equal(letters[0].audio_id,'audio-one');passed++;}
  else{assert(await page.getByRole('button',{name:'允许作为署名问答参考'}).isDisabled());assert(!calls.some(c=>c.p.endsWith('/model-use')));passed++;notes[0].status='accepted';notes[0].revision++;await page.locator('#refresh').click();await page.waitForFunction(()=>!Array.from(document.querySelectorAll('#notes button')).find(n=>n.textContent==='允许作为署名问答参考').disabled);await page.getByRole('button',{name:'允许作为署名问答参考'}).click();await page.waitForFunction(()=>document.getElementById('notes').textContent.includes('停用问答参考'));assert(notes[0].model_use_author_allowed);assert(!notes[0].model_use_owner_allowed);assert(!calls.some(c=>c.p.includes('/memories')||c.p.includes('/profile-candidates')));passed++;}
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);passed++;
  await page.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify({passed,fixture_only:true,checks:['persona mode','confirmed understanding leads','no technical badges','saved-answer speech only','stale answer cleared','separate reader voice grant','dedicated audio multipart','separate ASR consent','review before attachment','attributed model-use separately consented','private audio letter publish','mobile overflow']},null,2));
}
run().catch(e=>{console.error(e);process.exitCode=1;});
