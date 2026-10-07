const {test}=require('node:test');const assert=require('node:assert/strict');
const {model}=require('../app/workbench/live-garden.js');
test('only effective real IDs are mapped, unavailable and pending records are excluded',()=>{
 const story={episode_id:'ep_real',status:'ready',memories:[{memory_item_id:'m_real',content:'记忆',review_state:'active'},{memory_item_id:'m_old',review_state:'superseded'}]};
 const mapped=model([story,{...story,episode_id:'ep_secret',unavailable:true},{...story,episode_id:'ep_loading',status:'extracting'}]);
 assert.equal(mapped.length,1);assert.equal(mapped[0].episodeId,'ep_real');assert.deepEqual(mapped[0].memories.map(m=>m.id),['m_real']);
});
test('empty API creates no demo flowers',()=>assert.deepEqual(model([]),[]));
