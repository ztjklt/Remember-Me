import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Ajv from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
const read=name=>JSON.parse(fs.readFileSync(new URL('../schemas/'+name,import.meta.url)));
const schema=read('volcengine-voice-v2.schema.json');
const ajv=new Ajv({strict:false});addFormats(ajv);ajv.addSchema(read('integration-contract-v0.12.schema.json'));ajv.addSchema(schema);
const check=(name,value)=>ajv.getSchema(schema.$id+'#/$defs/'+name)(value);
test('v2 restores separately scoped capture and personal voices without vendor IDs',()=>{
 const request={cloud_consent_id:'cloud',voice_consent_id:'voice',policy:'current',voice_mode:'personal',recording_consent_id:'rec',speaker_consent_id:'speaker',enroll_owner_voice:true};
 assert(check('callRequest',request));
 assert(!check('callRequest',{...request,voice_id:'private-provider-id'}));
 assert(!check('callRequest',{...request,voice_mode:'unknown'}));
});
test('lease is independent of answer and acoustic status',()=>{
 assert(check('lease',{call_id:'vc-current'}));
 assert(!check('lease',{call_id:'vc-current',answer:{}}));
 assert(check('heartbeat',{call_id:'vc-current',turn_id:'ve_2',question:'原话',answer:null,failed:false,speaker_names:['小王'],speaker_message:null}));
 assert(!check('heartbeat',{call_id:'vc-current',turn_id:null,question:'',answer:null,failed:false,vectors:[1,0]}));
});
