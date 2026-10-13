async (page) => {
  const username='race_'+Date.now();
  const password='Test-'+Math.random().toString(36)+Math.random().toString(36);
  const registered=await page.request.post('http://127.0.0.1:8877/api/v1/accounts/register',{data:{username,password,display_name:'延迟响应测试'}});
  if(registered.status()!==201)throw new Error('Registration failed');
  await page.context().clearCookies();
  await page.evaluate(()=>localStorage.removeItem('remember-signed-out'));
  let release, captured=false, first=true;
  const blocked=new Promise(resolve=>release=resolve);
  await page.route('**/api/v1/workbench/spaces',async route=>{
    if(!first){await route.continue();return;}
    first=false;captured=true;await blocked;
    await route.fulfill({status:401,contentType:'application/json',body:JSON.stringify({error_code:'AUTH_INVALID',error_message:'Delayed old session failure'})});
  });
  await page.reload({waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelector('#accountEnter')!==null);
  for(let i=0;i<50&&!captured;i++)await page.waitForTimeout(100);
  if(!captured)throw new Error('Old bootstrap request was not captured');
  await page.locator('#username').fill(username);await page.locator('#password').fill(password);
  await page.locator('#accountEnter').click();await page.locator('#workspace').waitFor({state:'visible'});
  release();await page.waitForTimeout(500);
  await page.locator('[data-tab="sharing"]').click();await page.locator('#vocabulary').fill('方言测试：落屋表示回家。');
  const saved=page.waitForResponse(r=>r.url().endsWith('/vocabulary')&&r.request().method()==='PUT');
  await page.locator('#saveVocabulary').click();
  const response=await saved;
  if(response.status()!==200)throw new Error('Late old failure broke the new identity');
  await page.unroute('**/api/v1/workbench/spaces');
  await page.locator('#logout').click();await page.locator('#login').waitFor({state:'visible'});
  console.log(JSON.stringify({test:'late bootstrap failure cannot clear new login',passed:true}));
  return {test:'late bootstrap failure cannot clear new login',passed:true};
}
