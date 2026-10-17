// Node DOM stub tests for async/privacy behavior. Not browser rendering evidence.
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const script=fs.readFileSync(path.join(__dirname,'../app/receive/receipt.js'),'utf8');
function page(){
  class Element{
    constructor(tag){this.tag=tag;this.children=[];this.hidden=false;this.disabled=false;this.value='';this.textContent='';this.attributes={};}
    append(...children){this.children.push(...children)}
    replaceChildren(...children){this.children=children}
    set src(value){this.attributes.src=value}get src(){return this.attributes.src}
    getAttribute(name){return this.attributes[name]}removeAttribute(name){delete this.attributes[name]}
    setAttribute(name,value){this.attributes[name]=value}querySelector(){return null}
    addEventListener(){}focus(){}load(){}pause(){this.playing=false}async play(){this.playing=true}
  }
  const ids=['notice','gate','opened','sources','title','message','forYou','code','contact','send','verify','verifyForm','contactForm','sentTo','end'];
  const elements=Object.fromEntries(ids.map(id=>[id,new Element(id)]));elements.opened.hidden=true;
  const requests=[],intervals=[],urls=[],events={};let failContent=false,revoked=false,pendingAudio=null;
  const all=()=>Object.values(elements).flatMap(function walk(node){return [node,...node.children.flatMap(walk)]});
  const response=(body,status=200)=>({ok:status===200,status,json:async()=>body,blob:async()=>({size:10})});
  const fetch=async(url,options)=>{
    requests.push({url,options});
    if(url.endsWith('/challenges'))return response({challenge_id:'rc_test',contact_mask:'f***@example.test',retry_after_seconds:60});
    if(url.endsWith('/verify'))return response({session_token:'test-recipient-token',expires_at:new Date(Date.now()+60000).toISOString()});
    if(url.endsWith('/content')){
      if(failContent)throw new Error('offline');
      if(revoked)return response({error_message:'已撤销'},404);
      return response({recipient_label:'测试亲友',title:'专属测试',message:'只有这份内容',items:[{kind:'dedicated',id:'audio_test',title:'测试声音',has_audio:true}]});
    }
    if(url.includes('/audio/'))return pendingAudio?await pendingAudio:response({});
    return response({ended:true});
  };
  const document={hidden:false,getElementById:id=>elements[id],createElement:tag=>new Element(tag),
    querySelectorAll:tag=>all().filter(e=>e.tag===tag),addEventListener:(name,fn)=>events[name]=fn};
  vm.runInNewContext(script,{document,location:{hash:'#'+'a'.repeat(43),pathname:'/receive/'},history:{replaceState(){}},
    fetch,AbortController,setTimeout,clearTimeout,setInterval:(fn,ms)=>intervals.push({fn,ms}),Date,
    URL:{createObjectURL:()=>{urls.push('blob:test');return 'blob:test'},revokeObjectURL:()=>{}},
    window:{addEventListener:(name,fn)=>events[name]=fn}});
  return {elements,requests,intervals,urls,all,events,setFail:()=>failContent=true,setRevoked:()=>revoked=true,setAudio:p=>pendingAudio=p,response};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
async function unlock(p){
  p.elements.contact.value='family@example.test';p.elements.contactForm.onsubmit({preventDefault(){}});await settle();
  assert.equal(p.elements.verifyForm.hidden,false);
  p.elements.code.value='123456';p.elements.verifyForm.onsubmit({preventDefault(){}});await settle();
}
test('recipient verification leads straight to scoped content and authenticated audio',async()=>{
  const p=page();await unlock(p);assert.equal(p.elements.opened.hidden,false);
  assert.equal(p.elements.title.textContent,'专属测试');assert.equal(p.elements.code.value,'');assert.equal(p.elements.contact.value,'');
  p.all().find(x=>x.attributes['aria-label']==='播放原音').onclick();await settle();
  const media=p.requests.find(x=>x.url.includes('/audio/'));
  assert.equal(media.options.headers.Authorization,'Bearer test-recipient-token');assert.equal(media.options.credentials,'omit');assert.equal(media.options.cache,'no-store');
  assert.equal(p.urls.length,1);
});
test('revoked access clears content and active audio on next validation',async()=>{
  const p=page();await unlock(p);p.all().find(x=>x.attributes['aria-label']==='播放原音').onclick();await settle();
  const audio=p.all().find(x=>x.tag==='audio');assert.equal(audio.playing,true);
  p.setRevoked();await p.intervals.find(x=>x.ms===30000).fn();
  assert.equal(p.elements.opened.hidden,true);assert.equal(p.elements.sources.children.length,0);assert.equal(audio.playing,false);assert.equal(audio.src,undefined);
});
test('close during audio transfer discards a late response',async()=>{
  const p=page();await unlock(p);let finish;p.setAudio(new Promise(resolve=>finish=resolve));
  p.all().find(x=>x.attributes['aria-label']==='播放原音').onclick();await settle();p.elements.end.onclick();
  assert.equal(p.elements.opened.hidden,true);finish(p.response({}));await settle();
  assert.equal(p.urls.length,0);assert.equal(p.elements.title.textContent,'');
  assert.ok(p.requests.some(x=>x.options.method==='DELETE'));
});
test('lost content response after consuming OTP resets the verification form',async()=>{
  const p=page();p.setFail();await unlock(p);
  assert.equal(p.elements.opened.hidden,true);assert.equal(p.elements.verifyForm.hidden,true);
  assert.ok(p.requests.some(x=>x.options.method==='DELETE'));
});
