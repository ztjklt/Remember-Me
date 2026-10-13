const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../services/backend/app/workbench/narrative.js'),'utf8');
const context=vm.createContext({});
vm.runInContext(source+';globalThis.view=NarrativeView;',context);
test('links use shared evidence in confirmed visible records only',()=>{
  const person={id:'p',kind:'person',status:'confirmed',source_valid:true,evidence_ids:['a']};
  const story={id:'s',kind:'story',status:'confirmed',source_valid:true,evidence_ids:['a']};
  const rows=[story,{...story,id:'pending',status:'pending'},{...story,id:'stale',source_valid:false},{...story,id:'other',evidence_ids:['b']}];
  assert.deepEqual(Array.from(context.view.relatedStories(person,rows),r=>r.id),['s']);
  assert.equal(context.view.relatedStories(person,[]).length,0);
  assert.equal(context.view.relatedStories({...person,status:'pending'},rows).length,0);
});
