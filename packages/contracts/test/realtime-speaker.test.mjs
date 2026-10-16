import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Ajv from 'ajv/dist/2020.js';
const schema=JSON.parse(fs.readFileSync(new URL('../schemas/realtime-speaker-v1.schema.json',import.meta.url)));
const validate=new Ajv().compile(schema);
test('speaker events support named matches, unknown results and older agents',()=>{
 for(const value of [{type:'speaker',turn_id:'one',speaker_names:['小王','小李']},{type:'speaker',turn_id:'two',speaker_names:[],message:null},{type:'speaker',turn_id:'three',message:'旧事件'}])assert(validate(value));
});
test('speaker events require a turn and never carry acoustic vectors',()=>{
 for(const value of [{type:'speaker',speaker_names:['小王']},{type:'speaker',turn_id:'one',speaker_names:['小王','小王']},{type:'speaker',turn_id:'one',speaker_names:['']},{type:'speaker',turn_id:'one',vectors:[1,0]}])assert(!validate(value));
});
