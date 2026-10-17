import http from 'node:http';
import https from 'node:https';
import {readFile, stat} from 'node:fs/promises';
import {readFileSync, createReadStream, existsSync} from 'node:fs';
import {resolve, dirname, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {isIP} from 'node:net';

const here = dirname(fileURLToPath(import.meta.url));
const loopback = host => ['localhost', '127.0.0.1', '[::1]', '::1'].includes(host);
const types = {'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.json':'application/json; charset=utf-8','.webmanifest':'application/manifest+json','.svg':'image/svg+xml','.png':'image/png'};
const CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; media-src 'self' blob:; connect-src 'self'; worker-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'";
const safeMethods = new Set(['GET','HEAD','OPTIONS']);
const forwardHeaders = new Set(['content-type','content-length','authorization','cookie','range','if-range','idempotency-key']);

export function settings(env = process.env) {
  const host = env.HOST || '127.0.0.1', port = Number(env.PORT || 8770);
  const origin = new URL(env.WEB_PUBLIC_ORIGIN || `http://127.0.0.1:${port}`);
  const upstream = new URL(env.WEB_BACKEND_URL || 'https://39.108.183.47');
  for (const url of [origin, upstream]) {
    if(url.username || url.password || url.search || url.hash || url.pathname !== '/') throw Error('Use an origin URL without credentials, path, query or fragment.');
    if(url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback(url.hostname))) throw Error('Public access and upstream connections require HTTPS.');
  }
  if (!loopback(host) && origin.protocol !== 'https:') throw Error('A non-loopback bind requires an HTTPS WEB_PUBLIC_ORIGIN.');
  const bundledCA = resolve(here,'certs/backend.pem');
  const caFile = env.WEB_BACKEND_CA || (upstream.origin === 'https://39.108.183.47' ? (existsSync(bundledCA) ? bundledCA : resolve(here, '../android/app/src/internal/res/raw/remember_ecs_ip_demo.pem')) : '');
  const ca = caFile ? readFileSync(resolve(caFile)) : undefined;
  const demo = {};
  for (const role of ['reader','owner']) {
    const prefix = `WEB_DEMO_${role.toUpperCase()}_`;
    if(env[prefix+'USER'] && env[prefix+'PASSWORD']) demo[role] = {username:env[prefix+'USER'],password:env[prefix+'PASSWORD']};
  }
  const apk = env.WEB_APK_URL || '';
  if(apk && new URL(apk).protocol !== 'https:') throw Error('APK link must use HTTPS.');
  const demoSubject=env.WEB_DEMO_SUBJECT_ID || '';
  if(demoSubject && !/^subject_[a-zA-Z0-9_-]+$/.test(demoSubject)) throw Error('Invalid demo subject ID.');
  if(env.WEB_PRIVATE_DEMO==='1' && (!loopback(host)||!loopback(origin.hostname)))throw Error('Private local demo credentials must remain on loopback.');
  return {host,port,origin:origin.origin,upstream,ca,demo,demoSubject,apk,dist:resolve(here,'dist'),maxBytes:27*1024*1024};
}

function json(res, code, value) {
  res.writeHead(code, {'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});
  res.end(JSON.stringify(value));
}
function fail(res, code, message) {
  if(res.headersSent) return res.destroy();
  json(res, code, {error_code:'WEB_GATEWAY_ERROR',error_message:message});
}
function requestOptions(config, path, method, headers) {
  return {protocol:config.upstream.protocol,hostname:config.upstream.hostname,port:config.upstream.port || undefined,path,method,
    headers:{...headers,host:config.upstream.host,'accept-encoding':'identity'},
    agent:config.directAgent,ca:config.ca,rejectUnauthorized:true,servername:isIP(config.upstream.hostname) ? '' : config.upstream.hostname};
}
function transport(config) {return config.upstream.protocol === 'https:' ? https : http;}
function cookieHeaders(cookies, config) {
  return (cookies || []).filter(c => c.startsWith('remember_session=')).map(cookie => {
    let value = cookie.replace(/;\s*Domain=[^;]*/ig,'');
    if(new URL(config.origin).protocol === 'http:') value = value.replace(/;\s*Secure\b/ig,'');
    else if(!/;\s*Secure\b/i.test(value)) value += '; Secure';
    return value;
  });
}
async function bodyJSON(req, limit=2048) {
  const chunks=[];let size=0;
  for await (const chunk of req) {size+=chunk.length;if(size>limit)throw Error('Body too large');chunks.push(chunk);}
  return JSON.parse(Buffer.concat(chunks).toString());
}

export function createGateway(config) {
  const attempts = new Map();
  // A dedicated agent with an empty proxy environment also stays direct when
  // Node's global agent was started with NODE_USE_ENV_PROXY enabled.
  const Agent = config.upstream.protocol === 'https:' ? https.Agent : http.Agent;
  config.directAgent = new Agent({keepAlive:true,proxyEnv:{}});
  const server = http.createServer(async (req, res) => {
    res.setHeader('X-Content-Type-Options','nosniff');
    res.setHeader('Referrer-Policy','no-referrer');
    res.setHeader('Content-Security-Policy', CSP);
    res.setHeader('Permissions-Policy','microphone=(self), camera=(), geolocation=()');
    try {
      const incoming = new URL(req.url, config.origin);
      if(req.headers.host !== new URL(config.origin).host || incoming.origin !== config.origin) return fail(res,400,'访问地址与配置不一致。');
      if(!['GET','HEAD','POST','PATCH','PUT','DELETE','OPTIONS'].includes(req.method)) return fail(res,405,'不支持此操作。');
      const foreign = req.headers.origin && req.headers.origin !== config.origin;
      if(foreign || req.headers['sec-fetch-site'] === 'cross-site' || (!safeMethods.has(req.method) && req.headers.origin !== config.origin)) return fail(res,403,'请从当前页面发起操作。');
      const path = incoming.pathname;
      if(path === '/healthz' && req.method === 'GET') return json(res,200,{status:'ok',service:'remember-me-web'});
      if(path === '/web-config' && req.method === 'GET') return json(res,200,{demo_roles:Object.keys(config.demo),demo_subject_id:config.demoSubject || '',apk_url:config.apk});
      if(path === '/demo/login' && req.method === 'POST') {
        const {role} = await bodyJSON(req);
        if(!Object.hasOwn(config.demo,role)) return fail(res,404,'此体验身份尚未开放，请使用已有账号登录。');
        const peer = req.socket.remoteAddress || 'unknown', now=Date.now();
        for (const [key,times] of attempts) if(times.at(-1)<now-300000) attempts.delete(key);
        const recent = (attempts.get(peer)||[]).filter(t=>t>now-300000);
        if(recent.length>=8) return fail(res,429,'切换身份过于频繁，请稍后再试。');
        attempts.set(peer,[...recent,now]);
        const data = Buffer.from(JSON.stringify(config.demo[role]));
        const upstream = transport(config).request(requestOptions(config,'/api/v1/accounts/login','POST',{'content-type':'application/json','content-length':data.length}), response => {
          response.resume(); // Do not return the backend's bearer token in JSON.
          const cookies = cookieHeaders(response.headers['set-cookie'],config);
          if(response.statusCode !== 200 || !cookies.length) return fail(res,response.statusCode === 429 ? 429 : 503,'体验账号暂未连接成功，请稍后重试或使用已有账号。');
          res.setHeader('Set-Cookie',cookies);
          json(res,200,{ok:true,role,shared_demo:true});
        });
        upstream.setTimeout(20000,()=>upstream.destroy(Error('timeout')));
        upstream.on('error',()=>fail(res,502,'后端连接失败，请稍后重试。'));
        upstream.end(data);return;
      }
      if(path.startsWith('/api/v1/')) {
        // A fixed upstream; neither request URL nor headers may select a host.
        if(path.includes('..') || /%2f|%5c|%2e/i.test(path)) return fail(res,400,'无效接口路径。');
        if(Number(req.headers['content-length']||0)>config.maxBytes) return fail(res,413,'音频过大，请选择不超过 25 MB 的文件。');
        const headers=Object.fromEntries(Object.entries(req.headers).filter(([k])=>forwardHeaders.has(k)));
        // Browser CSRF is checked above. At the server boundary use the same
        // revocable bearer contract as Android, independent of upstream proxy
        // Host/Origin rewriting. Cookies from unrelated apps never leave here.
        if(headers.cookie) {
          const session=headers.cookie.split(';').map(c=>c.trim()).find(c=>c.startsWith('remember_session='));
          if(session && !headers.authorization) headers.authorization='Bearer '+session.slice('remember_session='.length);
          delete headers.cookie;
        }
        const upstream = transport(config).request(requestOptions(config,path+incoming.search,req.method,headers), response => {
          const selected={};
          for(const key of ['content-type','content-length','content-range','accept-ranges','etag','retry-after','x-request-id']) if(response.headers[key])selected[key]=response.headers[key];
          selected['cache-control']='no-store';
          const cookies=cookieHeaders(response.headers['set-cookie'],config);if(cookies.length)selected['set-cookie']=cookies;
          res.writeHead(response.statusCode,selected);response.pipe(res);
          response.on('error',()=>res.destroy());
        });
        let bytes=0;
        req.on('data',chunk=>{bytes+=chunk.length;if(bytes>config.maxBytes){fail(res,413,'音频过大，请选择不超过 25 MB 的文件。');upstream.destroy();}});
        upstream.setTimeout(180000,()=>upstream.destroy(Error('timeout')));
        upstream.on('error',()=>fail(res,502,'暂时连不上记忆服务。请保留原音，稍后再试。'));
        req.on('aborted',()=>upstream.destroy());
        res.on('close',()=>{if(!res.writableEnded)upstream.destroy();});
        req.pipe(upstream);return;
      }
      if(!['GET','HEAD'].includes(req.method)) return fail(res,405,'不支持此操作。');
      if(path === '/') {res.writeHead(302,{Location:config.demoSubject?'/app/':'/workbench/','Cache-Control':'no-store'});res.end();return;}
      const decoded=decodeURIComponent(path);
      const file=resolve(config.dist,'.'+decoded+(decoded.endsWith('/')?'index.html':''));
      if(!file.startsWith(config.dist+sep)) return fail(res,404,'页面不存在。');
      const info=await stat(file).catch(()=>null);
      if(!info?.isFile()) return fail(res,404,'页面不存在。');
      const ext=file.slice(file.lastIndexOf('.'));
      if(!(ext in types)) return fail(res,404,'页面不存在。');
      res.setHeader('Content-Type',types[ext]);res.setHeader('Cache-Control','no-cache');
      res.setHeader('Content-Length',info.size);
      if(req.method === 'HEAD')res.end();else createReadStream(file).pipe(res);
    } catch { fail(res,400,'请求未完成，请检查输入后重试。'); }
  });
  server.requestTimeout=180000;server.headersTimeout=15000;
  server.on('close',()=>config.directAgent.destroy());
  return server;
}

if(process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const config=settings();
  await readFile(resolve(config.dist,'build-info.json')); // Fail closed if not built.
  createGateway(config).listen(config.port,config.host,()=>console.log(`Remember Me Web: ${config.origin} — direct upstream, TLS verification enabled.`));
}
