import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import Ajv2020 from 'ajv/dist/2020.js';
const schema=JSON.parse(await readFile(new URL('../schemas/contact-entrustment-v1.schema.json',import.meta.url)));
const ajv=new Ajv2020({strict:false});ajv.addSchema(schema);
const check=name=>ajv.compile({$ref:schema.$id+'#/$defs/'+name});
test('contact receipt requires explicit confirmation and cannot grant an Actor or whole subject',()=>{
  const validate=check('Create');
  const body={recipient_label:'亲友',channel:'email',contact:'family@example.test',title:'留给你',message:'你好',
    sources:[{kind:'episode',id:'ep_test'}],source_version:'a'.repeat(64),days:30,confirmed:true,idempotency_key:'test'};
  assert.ok(validate(body),JSON.stringify(validate.errors));
  for(const change of [{confirmed:false},{recipient_actor_id:'actor_other'},{subject_id:'sub_other'},{days:91},{channel:'password'}])
    assert.equal(validate({...body,...change}),false);
});
test('recipient code verification is plan-bound and contains no owner token',()=>{
  const validate=check('Verify');
  const body={invite_token:'x'.repeat(43),challenge_id:'rc_test',code:'123456'};
  assert.ok(validate(body));
  for(const change of [{code:'12345'},{actor_token:'secret'},{challenge_id:''},{invite_token:''}])
    assert.equal(validate({...body,...change}),false);
});
