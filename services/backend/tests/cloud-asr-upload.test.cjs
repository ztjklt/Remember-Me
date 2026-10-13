const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../app/workbench/app.js'),'utf8');
const start=source.indexOf("on('upload','click'");
const end=source.indexOf("}finally{$('upload').disabled=false;}});",start)+"}finally{$('upload').disabled=false;}});".length;
function setup(configured=true, processing='cloud'){
 const state={caps:{stt_processing:processing,cloud_asr_policy:'acknowledged',stt_configured:configured},
  blob:new Blob(['audio'],{type:'audio/wav'}),space:{subject_id:'s'},uploadKey:'k'};
 const fields={ownSpeech:{checked:true},upload:{},captureMode:{value:'normal'},targetMemory:{value:''},timeText:{value:''}};
 let action;const sent=[];
 vm.runInNewContext(source.slice(start,end),{on:(_,__,fn)=>{action=fn},$:id=>fields[id],state,owner:()=>true,FormData,
  consent:async()=>{state.caps={...state.caps,cloud_asr_policy:'changed-without-ack'};return 'consent'},
  api:async(path,options)=>{sent.push(JSON.parse(options.body.get('metadata')));return {episode_id:'e'}},
  notice:()=>{},refresh:async()=>{},tab:()=>{}});
 return {action,sent};
}
test('upload uses the acknowledged policy even if refresh changes it during consent request',async()=>{
 const {action,sent}=setup();await action();assert.equal(sent[0].cloud_asr_policy,'acknowledged');
});
test('unknown cloud destination cannot be acknowledged for upload',async()=>{
 const {action,sent}=setup(false);await assert.rejects(action,/配置/);assert.equal(sent.length,0);
});
test('client mode blocks old audio-only upload before obtaining consent or sending audio',async()=>{
 const {action,sent}=setup(false,'client');await assert.rejects(action,/客户端/);assert.equal(sent.length,0);
});
test('client ASR with real server AI is not described as a fake model',()=>{
 const section=source.slice(source.indexOf('function capturePresentation('),source.indexOf('function notice('));
 const context={};vm.runInNewContext(section+';this.describe=capturePresentation;',context);
 const result=context.describe({stt_processing:'client',ai:'http',ai_available:true,live_configured:false,stt_configured:false});
 assert.match(result.notice,/客户端/);assert.doesNotMatch(result.notice,/替代模型/);assert.equal(result.serverUpload,false);
});
