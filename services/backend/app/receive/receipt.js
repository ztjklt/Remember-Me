'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const invite = location.hash.slice(1);
  history.replaceState(null, '', location.pathname);
  let challenge = '', token = '', expiry = 0, generation = 0, busy = false, polling = false, retryAt = 0;
  const requests = new Set(), urls = new Set();
  const root = '/api/v1/entrustment-receipts';
  const text = message => { $('notice').textContent = message; };
  function stopMedia() {
    document.querySelectorAll('audio').forEach(a => { a.pause(); a.removeAttribute('src'); a.load(); });
    urls.forEach(url => URL.revokeObjectURL(url)); urls.clear();
  }
  function clear(message = '') {
    generation++; requests.forEach(c => c.abort()); requests.clear(); stopMedia();
    token = ''; expiry = 0; $('opened').hidden = true; $('gate').hidden = false;
    $('sources').replaceChildren(); $('title').textContent = ''; $('message').textContent = '';
    $('forYou').textContent = ''; $('code').value = ''; challenge = ''; $('verifyForm').hidden = true;
    text(message); update();
  }
  function update() {
    $('send').disabled = busy || !/^[A-Za-z0-9_-]{43}$/.test(invite) || Date.now() < retryAt;
    $('verify').disabled = busy || !challenge;
    if (Date.now() < retryAt) $('send').textContent = `${Math.ceil((retryAt - Date.now()) / 1000)} 秒后可重发`;
    else $('send').textContent = '获取验证码';
  }
  async function api(path, body, method = body ? 'POST' : 'GET', audio = false) {
    const controller = new AbortController(); requests.add(controller);
    const epoch = generation, auth = token;
    const timeout = setTimeout(() => controller.abort(), audio ? 60000 : 20000);
    try {
      const response = await fetch(root + path, {method, credentials:'omit', cache:'no-store', referrerPolicy:'no-referrer',
        headers:{...(body ? {'Content-Type':'application/json'} : {}), ...(auth ? {Authorization:'Bearer ' + auth} : {})},
        body:body ? JSON.stringify(body) : undefined, signal:controller.signal});
      if (epoch !== generation || auth !== token) throw new Error('操作已取消。');
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        if (auth && [401,403,404,409,410].includes(response.status)) clear('内容已锁上，请重新核对领取状态。');
        throw new Error(data.error_message || '操作未完成，请稍后重试。');
      }
      const result = await (audio ? response.blob() : response.json());
      if (epoch !== generation || auth !== token) throw new Error('操作已取消。');
      return result;
    } finally { clearTimeout(timeout); requests.delete(controller); }
  }
  async function run(action) {
    if (busy) return; busy = true; update(); text('');
    try { await action(); } catch (e) { text(e.name === 'AbortError' ? '连接超时，请重试。' : e.message); }
    finally { busy = false; update(); }
  }
  function render(data) {
    $('gate').hidden = true; $('opened').hidden = false;
    if ($('unfold')) {
      $('unfold').hidden=false; $('letterPaper').hidden=true; $('sources').hidden=true;
      $('unfold').onclick=()=> { $('unfold').hidden=true; $('letterPaper').hidden=false; $('sources').hidden=false; $('unfold').setAttribute('aria-expanded','true'); };
    }
    $('forYou').textContent = '留给 ' + data.recipient_label;
    $('title').textContent = data.title; $('message').textContent = data.message;
    $('message').hidden = !data.message;
    $('sources').replaceChildren();
    for (const item of data.items) {
      const card = document.createElement('article'); card.className = 'card audio-card';
      const heading = document.createElement('h2'); heading.textContent = item.title; card.append(heading);
      if (item.has_audio) {
        const play = document.createElement('button'); play.className = 'ev-device';
        play.setAttribute('aria-label','播放原音');
        play.innerHTML='<span class="ev-device-top">原 声</span><span class="ev-grille" aria-hidden="true"></span><span class="ev-display"><span class="ev-device-state">听听那时的声音</span><span class="ev-device-clock">--:--</span></span><span class="ev-device-key" aria-hidden="true"><span class="ev-play-glyph"></span></span>';
        const audio = document.createElement('audio'); audio.controls = true; audio.preload = 'none'; audio.hidden = true;
        play.onclick = () => run(async () => {
          if(audio.getAttribute('src')) { if(audio.paused) await audio.play(); else audio.pause(); return; }
          const epoch = generation;
          const blob = await api('/audio/' + encodeURIComponent(item.kind) + '/' + encodeURIComponent(item.id), null, 'GET', true);
          if (epoch !== generation || Date.now() >= expiry) return;
          stopMedia(); const url = URL.createObjectURL(blob); urls.add(url);
          audio.src = url; audio.hidden = false;
          await audio.play().catch(() => text('声音已取回，请点击播放器继续。'));
        });
        audio.addEventListener('error', () => { if (audio.getAttribute('src')) text('这段声音未能播放，请重新取回。'); });
        const time = value => Number.isFinite(value) ? `${Math.floor(value/60).toString().padStart(2,'0')}:${Math.floor(value%60).toString().padStart(2,'0')}` : '--:--';
        const display = () => {
          const clock=play.querySelector('.ev-device-clock'), state=play.querySelector('.ev-device-state');
          if(clock) clock.textContent=time(audio.currentTime)+' / '+time(audio.duration);
          if(state) state.textContent=audio.paused?'轻触播放':'轻触暂停';
          play.setAttribute('aria-label',audio.paused?'播放原音':'暂停原音');
        };
        ['loadedmetadata','timeupdate','play','pause','ended'].forEach(name=>audio.addEventListener(name,display));
        card.append(play, audio);
      }
      if (item.text || item.supplement) {
        const detail = document.createElement('details'), summary = document.createElement('summary'), content = document.createElement('p');
        summary.textContent = '查看文字'; content.className = 'transcript';
        content.textContent = [item.text, item.supplement].filter(Boolean).join('\n\n');
        detail.append(summary, content); card.append(detail);
      }
      $('sources').append(card);
    }
  }
  $('contactForm').onsubmit = event => {
    event.preventDefault(); if (Date.now() < retryAt) return;
    run(async () => {
      challenge = ''; $('verifyForm').hidden = true;
      const data = await api('/challenges', {invite_token:invite, contact:$('contact').value.trim()});
      challenge = data.challenge_id; retryAt = Date.now() + data.retry_after_seconds * 1000;
      $('sentTo').textContent = '验证码已提交发送至 ' + data.contact_mask + '，5分钟内有效。';
      $('verifyForm').hidden = false; $('code').focus();
    });
  };
  $('verifyForm').onsubmit = event => {
    event.preventDefault(); run(async () => {
      const data = await api('/verify', {invite_token:invite, challenge_id:challenge, code:$('code').value.trim()});
      token = data.session_token; expiry = Date.parse(data.expires_at); $('code').value = ''; $('contact').value = '';
      if (!Number.isFinite(expiry) || expiry <= Date.now()) { clear('领取会话已过期。'); return; }
      try { render(await api('/content')); }
      catch (error) {
        // Verification consumes the code. Do not leave an unusable OTP form on a lost content response.
        if (token) {
          fetch(root + '/session', {method:'DELETE', credentials:'omit', keepalive:true,
            headers:{Authorization:'Bearer ' + token}}).catch(() => {});
          clear('本次内容未能打开，请稍后重新验证。');
        }
        throw error;
      }
    });
  };
  $('end').onclick = () => {
    // Closing must also work while an audio download is pending.
    const endingToken = token;
    clear('已关闭。再次打开需要重新验证。'); busy = false; update();
    if (endingToken) fetch(root + '/session', {method:'DELETE', credentials:'omit', keepalive:true,
      headers:{Authorization:'Bearer ' + endingToken}}).catch(() => {});
  };
  setInterval(() => {
    update(); if (token && Date.now() >= expiry) clear('本次查看已到期，请重新验证。');
  }, 1000);
  setInterval(async () => {
    if (!token || document.hidden || polling || busy) return;
    polling = true;
    try { await api('/content'); } catch (e) { if (token) clear('无法核验当前访问状态，内容已锁上。'); }
    finally { polling = false; }
  }, 30000);
  document.addEventListener('visibilitychange', () => { if (document.hidden) stopMedia(); });
  window.addEventListener('pagehide', () => { if (token) fetch(root + '/session', {method:'DELETE', credentials:'omit', keepalive:true, headers:{Authorization:'Bearer ' + token}}).catch(() => {}); clear(); });
  if (!/^[A-Za-z0-9_-]{43}$/.test(invite)) text('领取链接不完整，请使用对方提供的完整链接。');
  update();
})();
