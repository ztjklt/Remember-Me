import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';
import Ajv2020 from 'ajv/dist/2020.js';import addFormats from 'ajv-formats';
const schema=JSON.parse(fs.readFileSync(new URL('../schemas/integration-contract-v0.7.schema.json',import.meta.url)));
const ajv=new Ajv2020({strict:false});addFormats(ajv);const validate=ajv.compile(schema);
test('chat memory switch and private source view validate',()=>{
 assert.ok(validate({enabled:true}));assert.ok(validate({enabled:true,available_turn_count:0,forgotten_before:null,items:[],summaries:[]}));
 assert.equal(validate({enabled:true,actor_id:'forged'}),false);
});
test('v0.6 definitions remain compatible; only Twin response adds fields',()=>{
 const old=JSON.parse(fs.readFileSync(new URL('../schemas/integration-contract-v0.6.schema.json',import.meta.url)));
 for(const [name,value] of Object.entries(old.$defs))if(name!=='twinResponse')assert.deepEqual(schema.$defs[name],value);
 for(const [name,value] of Object.entries(old.$defs.twinResponse.properties))assert.deepEqual(schema.$defs.twinResponse.properties[name],value);
});
