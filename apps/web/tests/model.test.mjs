import test from 'node:test';
import assert from 'node:assert/strict';
import {availableStories,projectGarden,currentEvidence,personRows,confirmedUnderstandings,chooseSpace} from '../client/model.js';
import {SessionClient} from '../client/api.js';

function sample(){
  const evidence={evidence_id:'ev1',episode_id:'ep1',excerpt:'我喜欢淡茶。',source_type:'SUBJECT'};
  const memory={memory_item_id:'m1',content:'喜欢淡茶',review_state:'active',domain:'PREFERENCES',evidence:[evidence]};
  return {stories:[{episode_id:'ep1',status:'ready',reviewed:true,waiting_for_review:false,recorded_at:'2026-10-17',memories:[memory]}],narrative:{source_evidence:[evidence],records:[],understandings:[]},evidence,memory};
}
test('only the exact configured Chen subject is chosen, including with a stale prior session',()=>{
  const rows=[{subject_id:'subject_old',display_name:'陈守义'},{subject_id:'subject_chen',display_name:'陈守义 · 虚构演示'}];
  assert.equal(chooseSpace(rows,'subject_chen'),rows[1]);
  assert.equal(chooseSpace(rows,'subject_missing'),null);
  assert.equal(chooseSpace(rows,''),null);
});
test('garden rejects unreviewed, revoked or stale evidence without leaking titles',()=>{
  const {stories,narrative,evidence}=sample();
  narrative.records=[{id:'r1',kind:'story',status:'confirmed',source_valid:true,title:'a private story',evidence:[evidence]}];
  assert.equal(projectGarden(stories,narrative)[0].petals.length,1);
  for(const change of [{reviewed:false},{waiting_for_review:true},{unavailable:true},{status:'pending'}])assert.deepEqual(projectGarden([{...stories[0],...change}],narrative),[]);
  narrative.source_evidence=[{...evidence,excerpt:'This source has changed'}];
  assert.deepEqual(projectGarden(stories,narrative),[]);
  assert.deepEqual(personRows(stories,narrative),[]);
});
test('organized stories cover memories once; unrelated and empty legitimate recordings remain reachable',()=>{
  const {stories,narrative,evidence}=sample();
  narrative.records=[{id:'r1',kind:'story',status:'confirmed',source_valid:true,title:'茶',evidence:[evidence]}];
  stories.push({...stories[0],episode_id:'ep2',memories:[]});
  const garden=projectGarden(stories,narrative);
  assert.deepEqual(garden.map(g=>g.id),['record:r1','episode:ep2']);
  assert.equal(garden.flatMap(g=>g.petals).length,1);
});
test('pending or stale understandings never become confirmed personality facts',()=>{
  const {stories,narrative,evidence}=sample();
  narrative.understandings=['confirmed','pending','stale','conflicted'].map((status,i)=>({candidate_id:String(i),status,evidence:[evidence]}));
  assert.equal(confirmedUnderstandings(stories,narrative).length,1);
  narrative.understandings[0].counter_evidence=[{...evidence,evidence_id:'missing'}];
  assert.deepEqual(confirmedUnderstandings(stories,narrative),[]);
});
test('partial multi-source availability invalidates the entire dependent record',()=>{
  const {stories,narrative,evidence}=sample();
  assert.deepEqual(currentEvidence({evidence:[evidence,{...evidence,evidence_id:'ev2',episode_id:'ep2'}]},stories,narrative),[]);
  assert.equal(availableStories([...stories,stories[0]]).length,1);
});
test('late HTTP responses cannot repopulate a cleared identity',async()=>{
  const original=globalThis.fetch;let release;
  globalThis.fetch=()=>new Promise(resolve=>{release=()=>resolve({ok:true,json:async()=>({private:'previous identity'})});});
  try{const client=new SessionClient();const pending=client.request('/api/v1/workbench/spaces');client.reset();release();await assert.rejects(pending,e=>e.name==='AbortError');}
  finally{globalThis.fetch=original;}
});
