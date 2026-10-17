// Port of Android GardenProjection.kt. Keep permission/source rules in parity.
export const unique = (rows, key) => [...new Map(rows.map(r => [r[key], r])).values()];
export function availableStories(stories) {
  return unique(stories.filter(s => s.episode_id && s.status === 'ready' && s.reviewed && !s.waiting_for_review && !s.unavailable), 'episode_id');
}
export function currentEvidence(row, stories, narrative) {
  const visible = new Set(availableStories(stories).map(s => s.episode_id));
  const sources = new Map((narrative.source_evidence || []).map(e => [e.evidence_id, e]));
  const raw = row.evidence || [];
  if (!raw.length || raw.some(e => !e.evidence_id || !e.excerpt || !visible.has(e.episode_id) || sources.get(e.evidence_id)?.episode_id !== e.episode_id || sources.get(e.evidence_id)?.excerpt !== e.excerpt)) return [];
  return unique(raw, 'evidence_id');
}
export function projectGarden(stories, narrative) {
  const available = availableStories(stories), covered = new Set();
  const memories = unique(available.flatMap(s => s.memories || []).filter(m => m.memory_item_id && m.content && m.review_state === 'active'), 'memory_item_id');
  const petal = (m, evidence) => ({id:m.memory_item_id, content:m.content, domain:m.domain, evidence,
    label:m.origin === 'owner_supplement' ? '本人书面补充 · 不属于录音原话' : m.source_type === 'CALIBRATION' ? '本人确认的修订' : m.source_type === 'THIRD_PARTY' ? '系统整理 · 第三方转述' : m.source_type === 'AI_INFERENCE' ? '系统归纳 · 请结合依据理解' : '系统整理 · 来自讲述'});
  const organized = unique((narrative.records || []).filter(r => r.id && r.kind === 'story' && r.status === 'confirmed' && r.source_valid === true), 'id').flatMap(r => {
    const refs = currentEvidence(r, available, narrative); if (!refs.length) return [];
    const ids = new Set(refs.map(e => e.evidence_id));
    let petals = memories.flatMap(m => {const ev=currentEvidence(m, available, narrative); if (!ev.length || ev.some(e => !ids.has(e.evidence_id))) return []; covered.add(m.memory_item_id); return [petal(m, ev)];});
    if (!petals.length) petals=refs.map(e => ({id:'evidence:'+e.evidence_id,content:e.excerpt,label:'故事依据 · 核对文字',evidence:[e]}));
    const episodes=[...new Set(refs.map(e => e.episode_id))];
    return [{id:'record:'+r.id,title:r.title || '本人核对的故事',organized:true,episodes,facets:r.facets || [],petals,date:available.filter(s => episodes.includes(s.episode_id)).map(s => s.recorded_at).sort().at(-1)}];
  });
  const ungrouped=available.flatMap(s => {
    const petals=unique(s.memories || [], 'memory_item_id').flatMap(m => {
      if (covered.has(m.memory_item_id) || m.review_state !== 'active' || !m.content || !m.memory_item_id) return [];
      const ev=currentEvidence(m,available,narrative).filter(e => e.episode_id === s.episode_id);
      return ev.length ? [petal(m,ev)] : [];
    });
    if (!petals.length && ((s.memories || []).length || organized.some(r => r.episodes.includes(s.episode_id)))) return [];
    // An excerpt, not an invented story title or a manually maintained fixture.
    const title=(petals[0]?.evidence[0]?.excerpt || '一段已核对的讲述');
    return [{id:'episode:'+s.episode_id,title:title.length>26?title.slice(0,26)+'…':title,organized:false,episodes:[s.episode_id],facets:[],petals,date:s.recorded_at}];
  });
  return [...organized,...ungrouped].sort((a,b) => Number(b.organized)-Number(a.organized) || (b.date || '').localeCompare(a.date || '') || a.id.localeCompare(b.id));
}
export const domainFacet = {EPISODIC_MEMORY:'EXPERIENCE',RELATIONSHIPS:'RELATIONSHIPS',IDENTITY:'IDENTITY',PREFERENCES:'PRACTICES',BEHAVIOR_HABITS:'PRACTICES',VALUES_BELIEFS:'VALUES',DECISION_PATTERNS:'VALUES',EMOTIONAL_PATTERNS:'FEELINGS',GOALS:'WISHES',EXPRESSION:'EXPRESSION'};
export function personRows(stories, narrative) {
  return (narrative.records || []).filter(r => r.status === 'confirmed' && r.source_valid === true && currentEvidence(r,stories,narrative).length);
}
export function confirmedUnderstandings(stories, narrative) {
  return (narrative.understandings || []).filter(r => r.status === 'confirmed' && currentEvidence(r,stories,narrative).length && (!(r.counter_evidence || []).length || currentEvidence({evidence:r.counter_evidence},stories,narrative).length));
}
export function chooseSpace(spaces, subject) {
  // Exact server-configured subject; never guess by name or first array entry.
  return (spaces || []).find(s => s.subject_id === subject) || null;
}
export function flowerForm(id) {let n=0;for(const c of id)n=(Math.imul(n,31)+c.charCodeAt(0))|0;return ['front','side','cupped'][Math.abs(n)%3];}
