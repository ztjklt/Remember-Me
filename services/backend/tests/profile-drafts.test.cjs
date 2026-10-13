// Execute the production renderer with a minimal DOM, without a browser or API.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function node(tag,text){return {tag,text,children:[],listeners:{},value:'',append(...children){this.children.push(...children)},replaceChildren(...children){this.children=children},setAttribute(){},addEventListener(name,fn){this.listeners[name]=fn}};}
test('refresh while inspecting a source preserves update choice, target, reason and vague time',async()=>{
 const source=fs.readFileSync(require.resolve('../app/workbench/app.js'),'utf8');
 const renderer=source.slice(source.indexOf('async function renderProfiles('),source.indexOf("on('refreshProfile'"));
 const box=node('div');const drafts=new Map();
 const context=vm.createContext({node,button:(text,fn)=>node('button',text),$:()=>box,
   profileDrafts:drafts,state:{stories:[]},root:()=>'/test',api:async()=>({items:[]})});
 vm.runInContext(renderer,context);
 const candidate={candidate_id:'new',statement:'new',context:'work',status:'pending',domain:'PREFERENCES',kind:'habit',evidence_ids:[],counter_evidence_ids:[]};
 const data={jobs:[],items:[candidate,{...candidate,candidate_id:'old',status:'confirmed',stored_status:'confirmed'}]};
 await context.renderProfiles(data);
 let inputs=box.children[0].children.filter(n=>['select','textarea','input'].includes(n.tag));
 for(const [i,value] of ['CHANGE','old','核对后确认变化','退休以后'].entries()){inputs[i].value=value;inputs[i].listeners.input();}
 await context.renderProfiles(data); // focus may now be in the source dialog
 inputs=box.children[0].children.filter(n=>['select','textarea','input'].includes(n.tag));
 assert.deepEqual(inputs.map(n=>n.value),['CHANGE','old','核对后确认变化','退休以后']);
 drafts.clear();await context.renderProfiles(data);
 inputs=box.children[0].children.filter(n=>['select','textarea','input'].includes(n.tag));
 assert.equal(inputs[2].value,'');assert.equal(inputs[3].value,'');
});
