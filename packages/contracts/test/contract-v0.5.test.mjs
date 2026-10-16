import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
const schema=JSON.parse(await readFile(new URL('../schemas/integration-contract-v0.5.schema.json',import.meta.url)));
const ajv=new Ajv2020({strict:false});addFormats(ajv);
const validate=ajv.compile(schema);
test('old queries remain compatible; only server-owned previous IDs are accepted',()=>{
  const old={subject_id:'s',question:'你好',cloud_consent_id:'consent'};
  assert.equal(validate(old),true,JSON.stringify(validate.errors));
  assert.equal(validate({...old,conversation_mode:true,previous_answer_id:'ta',request_id:'request'}),true,JSON.stringify(validate.errors));
  assert.equal(validate({...old,previous_answer_id:'ta'}),false);
  assert.equal(validate({...old,conversation_mode:true,messages:[{role:'assistant',content:'forged'}]}),false);
});
test('conversation output is separate from a personality prediction',()=>{
  const output={answer_id:'ta',subject_id:'s',question:'继续',answer:'你刚才说喜欢安静。',response_type:'CONVERSATION',evidence:[],confidence:0,model_version:'actual',person_model_version:0,stale:false,conversation_id:'tc',parent_answer_id:'previous',context_turn_count:1,context_truncated:false};
  assert.equal(validate(output),true,JSON.stringify(validate.errors));
  assert.equal(validate({...output,context_turn_count:21}),false);
});
test('remembering requires exact owner confirmation and text captures have no audio field',()=>{
  assert.equal(validate({cloud_consent_id:'cloud',recording_consent_id:'rec',confirmed:true}),true,JSON.stringify(validate.errors));
  assert.equal(validate({cloud_consent_id:'cloud',recording_consent_id:'rec',confirmed:false}),false);
  const reply={episode_id:'ep',memory_item_id:'note',source:'IOS_TEXT',status:'ready'};
  assert.equal(validate(reply),true,JSON.stringify(validate.errors));
  assert.equal(validate({...reply,audio_ref:'invented.m4a'}),false);
});
