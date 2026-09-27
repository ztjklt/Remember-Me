async (page) => {
  const base='http://127.0.0.1:8770/assets/brand/forget-me-not/v1/';
  const directory='assets/brand/forget-me-not/v1/exports/';
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const exports=[];
  for(const [name,sizes] of [['mark-material',[256,1024]],['mark-flat',[32,128,512]],['mark-flat-dark',[128]],['mark-mono',[128]],['app-icon-light',[1024]],['app-icon-dark',[1024]],['app-foreground',[1024]]]) {
    for(const n of sizes){
      await page.setViewportSize({width:n,height:n});
      await page.goto(base+'preview.html?export='+name+'&size='+n);
      await page.locator('#export').evaluate(img=>img.decode());
      await page.locator('#export').screenshot({path:directory+name+'-'+n+'.png',omitBackground:true});
      exports.push({name,size:n});
    }
  }
  await page.goto(base+'preview.html');
  await page.setViewportSize({width:1280,height:1000});
  await page.screenshot({path:'output/playwright/brand-v1-overview.png',fullPage:true});
  const checks=[];
  for(const width of [360,430])for(const large of [false,true])for(const dark of [false,true])for(const variant of ['auto','material','flat','mono']){
    await page.setViewportSize({width,height:900});
    await page.evaluate(large=>document.documentElement.style.fontSize=large?'200%':'100%',large);
    await page.locator('#variant').selectOption(variant);
    await page.locator('#dark').setChecked(dark);
    for(const n of [24,96,160]){
      await page.locator('#size').fill(String(n));
      const value=await page.locator('#live').evaluate(el=>({variant:el.dataset.resolvedVariant,accessibleLabel:el.shadowRoot.querySelector('[role="img"]')?.getAttribute('aria-label'),overflow:document.documentElement.scrollWidth>innerWidth}));
      const expected=variant==='auto'?(n<64?'flat':'material'):variant;
      checks.push({width,large,dark,requested:variant,size:n,...value,passed:!value.overflow&&value.variant===expected&&value.accessibleLabel==='勿忘我品牌标识'});
    }
  }
  await page.locator('#wordmark').uncheck();
  if(await page.locator('#live').evaluate(el=>!!el.shadowRoot.querySelector('.name')))throw Error('Wordmark did not toggle');
  await page.locator('#wordmark').check();
  await page.locator('#copy').click();
  const copyStatus=await page.locator('#status').textContent();
  if(!copyStatus)throw Error('Copy feedback missing');
  await page.emulateMedia({reducedMotion:'reduce'});
  const animationCount=await page.evaluate(()=>document.getAnimations().length);
  if(animationCount!==0)throw Error('Unexpected animation');
  await page.evaluate(()=>document.documentElement.style.fontSize='100%');
  await page.locator('#variant').selectOption('auto');
  await page.locator('#size').fill('96');
  await page.locator('#dark').uncheck();
  await page.screenshot({path:'output/playwright/brand-v1-mobile.png',fullPage:true});
  await page.setViewportSize({width:1280,height:1000});
  await page.evaluate(()=>scrollTo(0,0));
  await page.screenshot({path:'output/playwright/brand-v1-final.png'});
  return {date:'2026-09-27',errors,exports,checks:checks.length,failures:checks.filter(x=>!x.passed),copyStatus,animationCount,native:'Adapters supplied; not integrated or compiled in native apps.'};
}
