const test = require('node:test');
const assert = require('node:assert/strict');
const {points, episodes} = require('./data.js');
let M;
try { M = require('./depth-model.js'); } catch (e) { if(e.code !== 'MODULE_NOT_FOUND') throw e; }
test('Related flowers retain every existing excerpt exactly once, without mixing sources', () => {
  assert.ok(M, 'the depth model must exist');
  const groups=M.build(points,episodes);
  assert.equal(groups.length,3);
  assert.deepEqual(groups.flatMap(g=>g.petals.flatMap(p=>p.ids)).sort(), points.map(p=>p.id).sort());
  for(const g of groups){
    assert.equal(g.petals.length,5);
    for(const id of g.petals.flatMap(p=>p.ids)) assert.equal(points.find(p=>p.id===id).episode,g.episode);
  }
  assert.equal(groups.find(g=>g.episode==='E03').petals.filter(p=>p.ids.length===0).length,1);
  assert.deepEqual(groups.find(g=>g.episode==='E01').petals[0].ids,['m10','m11','m12']);
});
test('Growth keeps old flower and petal identities; new fragments are reachable in bounded pages', () => {
  assert.ok(M, 'the depth model must exist');
  const base=M.build(points,episodes);
  const expanded=M.build([...points,...Array.from({length:302},(_,i)=>({id:`new-${i}`,episode:'E03',title:`后来 ${i}`}))],episodes);
  assert.deepEqual(expanded.slice(0,3),base);
  assert.equal(new Set(expanded.flatMap(g=>g.petals.flatMap(p=>p.ids))).size,317);
  const pages=M.pages(expanded);
  assert.ok(pages.every(p=>p.length<=3));
  assert.deepEqual(pages.flat(),expanded);
});
test('Navigation rejects empty or foreign petals, and back moves exactly one level', () => {
  assert.ok(M, 'the depth model must exist');
  const groups=M.build(points,episodes),garden={level:'garden',group:null,petal:null};
  const flower=M.move(garden,{group:'E03'},groups);
  assert.equal(flower.level,'flower');
  assert.deepEqual(M.move(flower,{petal:'E03-empty'},groups),flower);
  assert.deepEqual(M.move(flower,{petal:'E01-umbrella'},groups),flower);
  const petal=M.move(flower,{petal:'E03-notebook'},groups);
  assert.equal(petal.level,'petal');
  assert.deepEqual(M.move(petal,{back:true},groups),flower);
  assert.deepEqual(M.move(flower,{back:true},groups),garden);
  assert.deepEqual(M.move(garden,{group:'unknown'},groups),garden);
});
