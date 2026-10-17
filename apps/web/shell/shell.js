'use strict';
(() => {
  const byId = id => document.getElementById(id);
  const make = (tag, text, cls) => {const el=document.createElement(tag);if(text)el.textContent=text;if(cls)el.className=cls;return el;};
  let installPrompt=null;
  const tools=make('div',null,'app-tools'),install=make('button','像 App 一样使用');install.type='button';tools.append(install);document.querySelector('header').append(tools);
  const home=make('a','返回陈守义的花田');home.href='/app/';home.className='app-home-link';tools.prepend(home);
  const help=make('dialog',null,'app-help');help.setAttribute('aria-label','在手机上使用勿忘我');help.append(make('h2','把勿忘我放在手边。'),make('p','链接可以直接使用。添加到主屏幕后，可从桌面图标进入，支持时会以独立窗口打开。'));
  const instructions=make('ol');instructions.append(make('li','iPhone / iPad：使用 Safari 打开，点“分享”，再选“添加到主屏幕”。'),make('li','Android：使用 Chrome 或系统浏览器，打开菜单，选择“安装应用”或“添加到主屏幕”。'));
  help.append(instructions,make('p','故事和问答需要联网；手机录音时请保持页面在前台。原生 App 的蓝牙录音豆与连续语音能力，尚未接入这个网页版。'));
  const nativeInstall=make('button','添加到主屏幕');nativeInstall.hidden=true;nativeInstall.type='button';help.append(nativeInstall);
  const close=make('button','知道了');close.type='button';close.addEventListener('click',()=>help.close());help.append(close);document.body.append(help);
  install.addEventListener('click',()=>help.showModal());
  window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installPrompt=e;nativeInstall.hidden=false;});
  nativeInstall.addEventListener('click',async()=>{if(installPrompt){await installPrompt.prompt();installPrompt=null;nativeInstall.hidden=true;}});
  const network=make('div','当前离线。已经录下的声音请先下载保存；故事和问答恢复联网后再试。','app-network');network.hidden=navigator.onLine;document.querySelector('main').before(network);
  addEventListener('online',()=>network.hidden=true);addEventListener('offline',()=>network.hidden=false);
  if('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('/sw.js').catch(()=>{});
  const capture = document.body.classList.contains('capture-app');
  const space=byId('space');
  space?.addEventListener('change',()=>sessionStorage.setItem('remember-web-space',space.value));
  if(!capture && space) {
    const selectObserver=new MutationObserver(()=>{
      if(!space.options.length)return;
      selectObserver.disconnect();const previous=sessionStorage.getItem('remember-web-space');
      if([...space.options].some(o=>o.value===previous) && space.value!==previous){space.value=previous;space.dispatchEvent(new Event('change'));}
    });selectObserver.observe(space,{childList:true});
  }
  if(capture) {
    const rememberTab=()=>{const active=document.querySelector('[data-tab][aria-current="page"]');if(active)history.replaceState(null,'','#'+active.dataset.tab);};
    document.querySelectorAll('[data-tab]').forEach(el=>el.addEventListener('click',rememberTab));
    const observer=new MutationObserver(()=>{
      if(byId('workspace').hidden)return;
      observer.disconnect();
      const entry=new URL(location.href).searchParams.get('entry');
      if(entry==='reader') {
        const option=[...byId('space').options].find(o=>o.textContent.includes('授权读者'));
        if(option && option.value!==byId('space').value){byId('space').value=option.value;byId('space').dispatchEvent(new Event('change'));}
      } else if(!entry) {
        const previous=sessionStorage.getItem('remember-web-space');
        if([...space.options].some(o=>o.value===previous) && space.value!==previous){space.value=previous;space.dispatchEvent(new Event('change'));}
      }
      const identity=byId('identity');identity.textContent=identity.textContent.replace(/ · actor_[a-zA-Z0-9_-]+$/,'');
      const section=location.hash.slice(1) || (entry==='reader'?'archive':'today');
      document.querySelector(`[data-tab="${['today','archive','portrait','dialogue','sharing'].includes(section)?section:'today'}"]`)?.click();
      // Preserve existing role/consent handling; this is a presentation adapter.
    });observer.observe(byId('workspace'),{attributes:true,attributeFilter:['hidden']});
    for(const id of ['username','password'])byId(id).addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();byId('accountEnter').click();}});
    async function demo(role) {
      const buttons=[byId('demoReader'),byId('demoOwner')];buttons.forEach(b=>b.disabled=true);
      try {
        const response=await fetch('/demo/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role})});
        const data=await response.json();if(!response.ok)throw Error(data.error_message);
        localStorage.removeItem('remember-signed-out');sessionStorage.setItem('remember-web-demo','1');
        location.assign('/app/');
      } catch(e) {notice(e.message||'暂时无法进入体验，请稍后再试。',true);buttons.forEach(b=>b.disabled=false);}
    }
    byId('demoReader').addEventListener('click',()=>demo('reader'));byId('demoOwner').addEventListener('click',()=>demo('owner'));
    byId('accountEnter').addEventListener('click',()=>sessionStorage.removeItem('remember-web-demo'));
    byId('logout').addEventListener('click',()=>{sessionStorage.removeItem('remember-web-space');});
    Promise.all([fetch('/web-config').then(r=>r.json()),fetch('/api/v1/service-info').then(r=>{if(!r.ok)throw Error();return r.json();})]).then(([config,info])=>{
      byId('demoEntry').hidden=!config.demo_roles.length;byId('demoReader').hidden=true;byId('demoOwner').hidden=!config.demo_roles.includes('owner');
      byId('switchRegister').hidden=!info.registration_allowed;
      byId('registrationNote').textContent=info.registration_allowed?'已有账号可直接登录；也可以创建自己的空白空间。':'已有 App 账号可直接登录。独立账号由管理员提供。';
      if(config.apk_url){byId('apkDownload').href=config.apk_url;byId('apkDownload').hidden=false;}
    }).catch(()=>{byId('registrationNote').textContent='暂时连不上记忆服务，请检查连接后刷新；页面不会显示模拟数据。';});
    byId('audioFile').addEventListener('change',()=>{if(byId('audioFile').files[0]?.size>25*1024*1024){byId('upload').disabled=true;notice('这段音频超过 25 MB，请改选较短的文件。',true);}});
    addEventListener('beforeunload',e=>{if((state.recorder && state.recorder.state!=='inactive') || (state.blob && !state.uploaded)){e.preventDefault();e.returnValue='';}});
  }
  if(sessionStorage.getItem('remember-web-demo')) {
    const note=make('p','陈守义虚构演示空间 · 内容与同一账号的 App 同步。','demo-session-note');document.querySelector('#workspace')?.prepend(note);
  }
})();
