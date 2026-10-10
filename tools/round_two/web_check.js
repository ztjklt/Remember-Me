async (page) => {
  await page.reload();
  await page.getByRole('button',{name:'人物',exact:true}).click();
  const view=page.locator('#narrativeViews');
  await view.getByRole('button',{name:'人生足迹',exact:true}).click();
  await view.getByText('工作证与安稳过完一天',{exact:true}).waitFor();
  const search=view.getByRole('textbox',{name:'找故事、人名或一件旧物'});
  await search.fill('工作证');
  const consent=view.getByRole('checkbox',{name:'我同意将已核对的有效文字交由云端组织故事。'});
  await consent.check();
  const story=view.locator('article').filter({has:page.getByRole('heading',{name:'工作证与安稳过完一天',exact:true})});
  await story.locator('summary').click();
  await page.waitForTimeout(6200); // Explicitly exercise the app's five-second polling cycle.
  if(await search.inputValue()!=='工作证'||!await consent.isChecked()||!await story.locator('details').evaluate(el=>el.open))throw Error('Polling reset active user controls');
  for(const width of [360,412]) {
    await page.setViewportSize({width,height:844});
    await story.scrollIntoViewIfNeeded();
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Horizontal overflow at '+width);
    await page.screenshot({path:'output/playwright/round-two-'+width+'.png'});
  }
  await page.emulateMedia({reducedMotion:'reduce',colorScheme:'dark'});
  await page.evaluate(()=>document.documentElement.style.setProperty('font-size','200%','important'));
  await story.getByRole('button',{name:'查看变化历史',exact:true}).click();
  await story.getByText('版本 3 · confirm · 工作证与安稳过完一天',{exact:true}).waitFor();
  await page.screenshot({path:'output/playwright/round-two-large-text.png'});
  await page.reload();await page.getByRole('button',{name:'今天',exact:true}).click();
  await page.getByRole('button',{name:'了解故事：工作证与安稳过完一天',exact:true}).click();
  if(!await view.getByRole('heading',{name:'工作证与安稳过完一天',exact:true}).isVisible())throw Error('Garden did not open its actual story');
  return {polling:'passed',widths:[360,412],largeTextHistory:'passed',reducedMotion:'exercised',gardenStoryNavigation:'passed',microphone:'not tested'};
}
