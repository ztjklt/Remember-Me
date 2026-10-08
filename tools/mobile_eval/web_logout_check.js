async (page) => {
  const username='web_'+Date.now();
  const password='Test-'+Math.random().toString(36)+Math.random().toString(36);
  const result=await page.request.post('http://127.0.0.1:8877/api/v1/accounts/register',{data:{username,password,display_name:'网页退出测试'}});
  if(result.status()!==201)throw new Error('Registration failed: '+result.status());
  await page.evaluate(()=>localStorage.removeItem('remember-signed-out'));
  await page.reload();await page.locator('#workspace').waitFor({state:'visible'});
  await page.route('**/api/v1/accounts/logout',route=>route.abort());
  await page.locator('#logout').click();await page.locator('#login').waitFor({state:'visible'});
  await page.unroute('**/api/v1/accounts/logout');await page.reload();
  await page.waitForTimeout(1500);
  const stayedSignedOut=await page.locator('#login').isVisible();
  console.log(JSON.stringify({test:'offline logout remains signed out after reload',passed:stayedSignedOut}));
  if(!stayedSignedOut)throw new Error('Private workspace reopened after failed logout');
  return {test:'offline logout remains signed out after reload',passed:stayedSignedOut};
}
