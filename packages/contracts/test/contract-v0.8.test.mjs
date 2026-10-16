import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
const schema=JSON.parse(fs.readFileSync(new URL('../schemas/integration-contract-v0.8.schema.json',import.meta.url)));
const ajv=new Ajv2020({strict:false});addFormats(ajv);ajv.addSchema(schema);
const request=ajv.compile({$ref:schema.$id+'#/$defs/voiceCallRequest'});
const old={cloud_consent_id:'cloud',voice_consent_id:'voice',policy:'rv1-fixture'};
test('default voice is additive and still needs independent consents',()=>{
 assert.ok(request(old));assert.ok(request({...old,voice_mode:'default'}));assert.ok(request({...old,voice_mode:'personal'}));
 assert.equal(request({...old,voice_mode:'unknown'}),false);
 const noVoice={...old,voice_mode:'default'};delete noVoice.voice_consent_id;assert.equal(request(noVoice),false);
});
test('unrelated v0.7 definitions keep their exact shapes',()=>{
 const previous=JSON.parse(fs.readFileSync(new URL('../schemas/integration-contract-v0.7.schema.json',import.meta.url)));
 for(const [name,value] of Object.entries(previous.$defs))if(!['realtimeVoiceCapabilities','voiceCallRequest','voiceCallTicket'].includes(name))assert.deepEqual(schema.$defs[name],value);
});
