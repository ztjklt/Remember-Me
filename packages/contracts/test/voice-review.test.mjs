import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Ajv from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
const schema=JSON.parse(fs.readFileSync(new URL('../schemas/voice-review-v1.schema.json',import.meta.url)));
const ajv=new Ajv({strict:false}); addFormats(ajv); ajv.addSchema(schema);
const check=(name,value)=>ajv.getSchema(schema.$id+'#/$defs/'+name)(value);
test('voice acceptance is tied to an explicit profile and boolean decision',()=>{
 assert(check('reviewRequest',{profile_id:'rvp_own',accepted:true}));
 assert(!check('reviewRequest',{profile_id:'rvp_own',accepted:'yes'}));
 assert(!check('reviewRequest',{profile_id:'rvp_own',accepted:true,voice_id:'vendor-secret'}));
 assert(!check('reviewRequest',{accepted:true}));
});
test('review and retirement expose no vendor credentials',()=>{
 assert(check('review',{profile_id:'rvp_own',status:'pending',reviewed_at:null,previewed_at:null}));
 assert(check('retryReceipt',{retired_profile_id:'rvp_own',status:'retired'}));
 assert(!check('review',{profile_id:'rvp_own',status:'ready',reviewed_at:null,previewed_at:null}));
 assert(!check('selection',{profile_id:'rvp_own',delete_all:true}));
});
