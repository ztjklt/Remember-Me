/* Local curation of existing fictional excerpts, not inferred relationships or a shared API. */
(function(root){
  const curated=[
    {id:'E03',episode:'E03',title:'厨房里的往事',seed:341,rotation:8,petals:[
      ['notebook','妈妈的小本子',['m1']],['taste','不一样，也喜欢',['m3']],
      ['slow','愿意慢下来',['m7']],['window','玻璃上的小圈',['m14']]]},
    {id:'E01',episode:'E01',title:'雨夜，留着灯',seed:823,rotation:-12,petals:[
      ['umbrella','借伞与回应',['m10','m11','m12']],['rain','窗边的灯与雨',['m13']],
      ['reading','有人慢慢读书',['m15']],['supper','留好的饭菜',['m2']],['waiting','家人的等待',['m5']]]},
    {id:'E02',episode:'E02',title:'那碗凉了的汤',seed:713,rotation:15,petals:[
      ['soup','一碗凉了的汤',['m4']],['calendar','日历里的约定',['m6']],
      ['tell','早点告诉她',['m8']],['listen','停下那句解释',['m9']]]}
  ];
  function build(points,episodes){
    const byId=new Map(points.map(p=>[p.id,p])),used=new Set();
    const fill=g=>{while(g.petals.length<5)g.petals.push({id:`${g.id}-empty${g.petals.length===4?'':g.petals.length}`,title:'待绽放',ids:[]});return g;};
    const groups=curated.map(c=>fill({...c,petals:c.petals.map(([key,title,ids])=>({id:`${c.id}-${key}`,title,ids:ids.filter(id=>{const p=byId.get(id);if(!p||p.episode!==c.episode)return false;used.add(id);return true;})})).filter(p=>p.ids.length)})).filter(g=>g.petals.some(p=>p.ids.length));
    // Uncurated future excerpts remain separate. Overflow flowers never change existing petal assignments.
    const extra=new Map();
    for(const p of points)if(!used.has(p.id)){if(!extra.has(p.episode))extra.set(p.episode,[]);extra.get(p.episode).push(p);}
    for(const [episode,list] of extra)for(let i=0;i<list.length;i+=5){
      const batch=list.slice(i,i+5),id=`${episode}-more-${batch[0].id}`;
      groups.push(fill({id,episode,title:`${episodes[episode]?.title||'待整理的回忆'} · ${i/5+1}`,seed:341+i,rotation:8,petals:batch.map(p=>({id:`${id}-${p.id}`,title:p.title,ids:[p.id]}))}));
    }
    return groups;
  }
  function pages(groups){return Array.from({length:Math.ceil(groups.length/3)},(_,i)=>groups.slice(i*3,i*3+3));}
  function move(route,action,groups){
    if(action.home||action.back&&route.level==='flower')return {level:'garden',group:null,petal:null};
    if(action.back&&route.level==='petal')return {level:'flower',group:route.group,petal:null};
    const group=groups.find(g=>g.id===(action.group||route.group));
    if(action.group&&group)return {level:'flower',group:group.id,petal:null};
    if(action.petal&&route.level==='flower'&&group?.petals.some(p=>p.id===action.petal&&p.ids.length))return {level:'petal',group:group.id,petal:action.petal};
    return route;
  }
  const api={build,pages,move};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.GardenDepthModel=api;
})(typeof window==='undefined'?{}:window);
