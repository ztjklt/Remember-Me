import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Ajv from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
const read=name=>JSON.parse(fs.readFileSync(new URL('../schemas/'+name,import.meta.url)));
const schema=read('volcengine-voice-v1.schema.json');
const ajv=new Ajv({strict:false});addFormats(ajv);ajv.addSchema(read('integration-contract-v0.12.schema.json'));ajv.addSchema(schema);
const check=(name,value)=>ajv.getSchema(schema.$id+'#/$defs/'+name)(value);
const id='vc_'+'a'.repeat(32);
const ticket={transport:'volcengine',call_id:id,room:id,participant_identity:'user_'+id,bot_identity:'twin_'+id,app_id:'b'.repeat(24),token:'ephemeral',expires_at:'2026-10-16T12:00:00Z',voice_mode:'default'};
test('domestic tickets are independent from LiveKit and contain no provider secrets',()=>{
 assert(check('ticket',ticket));
 for(const key of ['app_key','access_key','voice_id','livekit_url'])assert(!check('ticket',{...ticket,[key]:'private'}));
 assert(!check('ticket',{...ticket,transport:'livekit'}));
});
test('domestic request cannot silently enable capture or use an old provider voice',()=>{
 const request={cloud_consent_id:'cloud',voice_consent_id:'voice',policy:'current',voice_mode:'default'};
 assert(check('callRequest',request));
 assert(!check('callRequest',{...request,voice_mode:'personal'}));
 assert(!check('callRequest',{...request,recording_consent_id:'capture'}));
});
test('heartbeat and interrupt preserve explicit failure and scoped turns',()=>{
 assert(check('heartbeat',{call_id:id,turn_id:null,question:'',answer:null,failed:false}));
 assert(check('interrupt',{turn_id:'ve_2'}));
 assert(!check('interrupt',{turn_id:'',text:'arbitrary synthesis'}));
});
