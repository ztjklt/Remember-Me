async (page) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('http://127.0.0.1:8768/docs/mobile-ui/prototype.html');
  await page.setViewportSize({width:1200,height:1100});
  await page.locator('[data-action="record"]').click();
  await page.locator('[data-action="start"]').click();
  await page.getByRole('button',{name:'同意并开始',exact:true}).click();
  await page.getByRole('button',{name:'暂停录音',exact:true}).click();
  await page.getByRole('button',{name:'继续录音',exact:true}).click();
  await page.getByRole('button',{name:'完成并保存',exact:true}).click();
  await page.getByRole('button',{name:'转成文字',exact:true}).click();
  await page.getByRole('heading',{name:'核对文字',exact:true}).waitFor();
  await page.getByRole('status').filter({hasText:'先核对'}).waitFor();
  await page.locator('#transcript').fill('修改后的文字 <保留>');
  await page.getByRole('button',{name:'只保存核对文字',exact:true}).click();
  if(await page.locator('#transcript').inputValue()!=='修改后的文字 <保留>') throw Error('Review text lost');
  await page.getByRole('button',{name:'确认文字并整理记忆',exact:true}).click();
  await page.getByRole('button',{name:'同意并整理',exact:true}).click();
  await page.getByRole('heading',{name:'当时说过的话'}).waitFor();
  await page.getByRole('button',{name:'删除这条记忆',exact:true}).click();
  await page.getByRole('button',{name:'删除记忆',exact:true}).click();
  await page.getByRole('status').filter({hasText:'还没有可显示的内容'}).waitFor();
  await page.getByRole('tab',{name:'录音',exact:true}).click();
  await page.locator('#query').fill('不存在');
  await page.getByRole('status').filter({hasText:'没有找到相关内容'}).waitFor();
  await page.locator('#query').fill('桂花');
  if(await page.locator('#results .entry').count()!==1) throw Error('Search failed');
  const result=[];
  for(const [platform,width] of [['android',360],['android',412],['ios',375],['ios',430]]) {
    for(const large of [false,true]) {
      for(const target of ['home','record','archive','review','memory','profile']) {
        await page.setViewportSize({width:1200,height:1100});
        await page.locator('#platform').selectOption(platform);
        await page.locator('#large').setChecked(large);
        await page.locator('#dark').setChecked(large);
        await page.locator('#reduce').setChecked(large);
        await page.locator('.jump [data-go="'+target+'"]').click();
        await page.setViewportSize({width,height:850});
        const measure=await page.evaluate(()=>{
          const screen=document.querySelector('#screen'), dock=document.querySelector('#dock');
          return {horizontalOverflow:screen.scrollWidth>screen.clientWidth+1,
            viewportOverflow:document.documentElement.scrollWidth>innerWidth,
            dockBottom:dock.getBoundingClientRect().bottom, viewport:innerHeight,
            scrollArea:screen.clientHeight};
        });
        result.push({platform,width,large,page:target,...measure});
        if(target==='home'||target==='review'||(target==='record'&&large)) await page.screenshot({animations:'disabled',path:'output/playwright/'+platform+'-'+width+'-'+target+(large?'-large-dark':'')+'.png'});
      }
    }
  }
  await page.setViewportSize({width:1200,height:1100});
  await page.locator('#large').uncheck(); await page.locator('#dark').uncheck();
  await page.locator('.jump [data-go="review"]').click();
  for(const scenario of ['error','loading','content']) {
    await page.locator('#scenario').selectOption(scenario);
    await page.screenshot({animations:'disabled',path:'output/playwright/state-'+scenario+'.png'});
  }
  await page.locator('#scenario').selectOption('empty');
  await page.locator('.jump [data-go="home"]').click();
  await page.getByRole('status').filter({hasText:'从第一段声音开始'}).waitFor();
  return {errors,cases:result,flow:'passed',failures:result.filter(c=>c.horizontalOverflow||c.viewportOverflow||c.dockBottom>c.viewport+1||c.scrollArea<100)};
}