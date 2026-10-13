// Keep navigation nodes (and keyboard focus) alive across page updates.
let lastNavigationPlatform;
let transitionSequence=0;
const pageScroll=new Map();
const reducedMotion=()=>document.documentElement.classList.contains('reduce') || matchMedia('(prefers-reduced-motion: reduce)').matches;
function finishPageMotion(){
  $('#screen').getAnimations().forEach(animation=>animation.cancel());
  document.querySelectorAll('.outgoing-page,.outgoing-scenery').forEach(element=>element.remove());
}
function navigate(next){
  if(next===page)return;
  MemoryGarden.teardown();
  finishPageMotion();
  pageScroll.set(page,$('#screen').scrollTop);
  const snapshot=reducedMotion()?null:GardenPetalMotion.snapshot();
  page=next;playing=false;render();
  $('#screen').scrollTop=pageScroll.get(next)||0;
  if(snapshot)GardenPetalMotion.dissolve(snapshot);

}
function renderNavigation(){
  const nav=$('#nav'), platform=$('#platform').value;
  const tabs=[['home','sun','今天'],['archive','book','档案'],...(platform==='ios'?[['conversation','chat','对话']]:[]),['profile','person','我的']];
  nav.classList.toggle('hidden',!['home','archive','profile','conversation','system'].includes(page));
  if(platform!==lastNavigationPlatform){
    nav.innerHTML=tabs.map(([destination,glyph,label])=>`<button data-go="${destination}">${icon(glyph)}<span>${label}</span></button>`).join('');
    nav.style.setProperty('--nav-count',tabs.length);
    lastNavigationPlatform=platform;
  }
  nav.querySelectorAll('button').forEach(button=>{
    if(button.dataset.go===page)button.setAttribute('aria-current','page');
    else button.removeAttribute('aria-current');
  });
  const index=tabs.findIndex(([destination])=>destination===page);
  nav.classList.toggle('no-selection',index<0);
  if(index>=0)nav.style.setProperty('--nav-index',`${index*100}%`);
}
function selectArchiveTab(next){
  if(mode===next)return;
  MemoryGarden.teardown();finishPageMotion();
  const snapshot=reducedMotion()?null:GardenPetalMotion.snapshot();
  mode=next;
  const tabs=$('.tabs');
  tabs.style.setProperty('--tab-index',mode==='recordings'?'0%':'100%');
  tabs.querySelectorAll('button').forEach(button=>{
    button.setAttribute('aria-selected',String(button.dataset.action===mode));
    button.tabIndex=button.dataset.action===mode?0:-1;
  });
  $('#results').setAttribute('aria-labelledby',`tab-${mode}`);
  $('#results').innerHTML=archiveResults();
  MemoryGarden.mount();
  $('#results').classList.remove('results-enter');
  const focus=()=>{if(mode===next)(next==='memories'?$('.depth-title h1'):$(`#tab-${next}`))?.focus({preventScroll:true});};
  if(snapshot)GardenPetalMotion.dissolve(snapshot,{finish:focus});else focus();

}
document.addEventListener('keydown',event=>{
  const tab=event.target.closest('.tabs [role=tab]');
  if(!tab || !['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  event.preventDefault();
  const next=event.key==='Home'?'recordings':event.key==='End'?'memories':mode==='recordings'?'memories':'recordings';
  selectArchiveTab(next);
  $(`#tab-${next}`).focus();
});
