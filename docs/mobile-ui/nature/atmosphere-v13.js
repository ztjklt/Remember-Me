(()=>{
  const phone=document.querySelector('.phone'),html=document.documentElement,media=matchMedia('(prefers-reduced-motion: reduce)');
  let paused=false;
  function update(){
    const reduced=html.classList.contains('reduce')||media.matches;
    phone.classList.toggle('clouds-paused',paused||reduced||document.hidden||phone.dataset.page!=='home');
    const b=document.querySelector('[data-cloud-toggle]');if(!b)return;
    b.disabled=reduced;b.setAttribute('aria-pressed',String(paused||reduced));
    b.setAttribute('aria-label',reduced?'减少动态已开启，云景静止':paused?'继续云朵飘动':'暂停云朵飘动');
    b.querySelector('[data-cloud-label]').textContent=reduced?'静止云景':paused?'继续流云':'暂停流云';
  }
  document.addEventListener('click',e=>{if(e.target.closest('[data-cloud-toggle]')){paused=!paused;update();}});
  document.addEventListener('visibilitychange',update);media.addEventListener('change',update);
  new MutationObserver(update).observe(html,{attributes:true,attributeFilter:['class']});
  new MutationObserver(update).observe(phone,{attributes:true,attributeFilter:['data-page']});
  // Page content may be replaced without a route change (e.g. platform or empty-state preview).
  new MutationObserver(update).observe(document.querySelector('#screen'),{childList:true});
  update();
})();
