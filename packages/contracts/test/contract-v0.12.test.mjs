import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Ajv from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
const current=JSON.parse(fs.readFileSync(new URL('../schemas/integration-contract-v0.12.schema.json',import.meta.url)));
const old=JSON.parse(fs.readFileSync(new URL('../schemas/integration-contract-v0.11.schema.json',import.meta.url)));
const ajv=new Ajv({strict:false});addFormats(ajv);ajv.addSchema(current);
const check=(name,value)=>ajv.getSchema(current.$id+'#/$defs/'+name)(value);
test('v0.12 retains every v0.11 definition',()=>{for(const [key,value] of Object.entries(old.$defs))assert.deepEqual(current.$defs[key],value);});
test('coverage has provenance, denominator and ceiling',()=>{
 const names=['IDENTITY','EPISODIC_MEMORY','RELATIONSHIPS','PREFERENCES','VALUES_BELIEFS','DECISION_PATTERNS','EXPRESSION'];
 const value={subject_id:'s',model_version:3,metric_version:'seven-domains-five-sources-v1',metric:'evidence_source_coverage',percentage:0,cap_percentage:95,covered_units:0,target_units:35,domains:names.map(domain=>({domain,source_count:0,target_sources:5,percentage:0,episode_ids:[]})),explanation:'Source coverage, not fidelity.'};
 assert(check('modelCoverage',value));assert(!check('modelCoverage',{...value,percentage:100}));assert(!check('modelCoverage',{...value,target_units:0}));
});
test('voice identity status cannot return private vectors',()=>{
 const value={available:true,items:[{identity_id:'v',label:'小王',role:'subject',model_version:'we-speaker-sha',status:'registered',source_count:1}],enrollment_prompt:'介绍自己',notice:'Auxiliary only.'};
 assert(check('voiceIdentityList',value));value.items[0].vectors=[1,0];assert(!check('voiceIdentityList',value));
});
test('unlock never contains a subject-wide permission or raw secret',()=>{
 const value={unlock_token:'opaque',expires_at:'2026-10-15T01:00:00Z'};assert(check('entrustmentUnlock',value));assert(!check('entrustmentUnlock',{...value,secret:'password'}));
});
