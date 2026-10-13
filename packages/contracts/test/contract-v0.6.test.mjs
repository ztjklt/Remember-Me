import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
const schema=JSON.parse(fs.readFileSync(new URL('../schemas/integration-contract-v0.6.schema.json',import.meta.url)));
const ajv=new Ajv2020({strict:false});addFormats(ajv);
const root=ajv.compile(schema);
const request={cloud_consent_id:'cloud',voice_consent_id:'voice',policy:'rv1-fixture'};
const ticket={call_id:'vc_'+'a'.repeat(32),room:'vc_'+'a'.repeat(32),participant_identity:'user_vc_'+'a'.repeat(32),
  livekit_url:'wss://rtc.fixture.invalid',token:'ephemeral-fixture',expires_at:'2026-10-13T08:00:00Z'};
test('voice tickets and separate grant requests validate',()=>{assert.ok(root(request));assert.ok(root(ticket));});
test('plain sockets and provider secrets never fit public tickets',()=>{
  assert.equal(root({...ticket,livekit_url:'ws://rtc.fixture.invalid'}),false);
  assert.equal(root({...ticket,api_secret:'provider-secret'}),false);
  assert.equal(root({...ticket,provider_voice_id:'provider-private'}),false);
});
test('old v0.5 definitions retain their exact shapes',()=>{
 const previous=JSON.parse(fs.readFileSync(new URL('../schemas/integration-contract-v0.5.schema.json',import.meta.url)));
 for(const [name,value] of Object.entries(previous.$defs))assert.deepEqual(schema.$defs[name],value);
});
