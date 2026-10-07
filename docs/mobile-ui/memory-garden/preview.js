(() => {
  const params=new URLSearchParams(location.search),html=document.documentElement;
  html.classList.toggle('presentation',params.get('demo')==='1');
  html.classList.toggle('wide-preview',params.get('wide')==='1');
  // Explicitly preview the user's requested translucency; system and solid options remain available.
  html.classList.add('preview-translucency');
  const select=document.getElementById('surface-material');
  select.addEventListener('change',()=>{
    html.classList.toggle('preview-translucency',select.value==='translucent');
    html.classList.toggle('solid-surfaces',select.value==='solid');
  });
  const phone=document.querySelector('.phone'),out=document.getElementById('preview-size');
  new ResizeObserver(()=>{out.textContent=`当前 App 内容画布 ${phone.clientWidth} × ${phone.clientHeight} CSS px。桌面演示模式：390 × 844；手机浏览器随可用视口适配。`;}).observe(phone);
})();
