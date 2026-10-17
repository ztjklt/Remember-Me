import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import vm from 'node:vm';
import {createGateway, settings} from '../server.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
async function start(server){await new Promise(r=>server.listen(0,'127.0.0.1',r));return `http://127.0.0.1:${server.address().port}`;}
async function stop(server){server.closeAllConnections();await new Promise(r=>server.close(r));}
async function harness(t, handler, additions={}) {
  const backend = http.createServer(handler), backendURL=await start(backend);
  const config={host:'127.0.0.1',port:0,origin:'',upstream:new URL(backendURL),ca:undefined,demo:{reader:{username:'fictional',password:'test-only-password'}},apk:'',dist:resolve(root,'dist'),maxBytes:64,...additions};
  const gateway=createGateway(config);config.origin=await start(gateway);
  t.after(async()=>{await stop(gateway);await stop(backend);});return {config,gateway};
}

test('configuration rejects public plaintext, credentials and path injection',()=>{
  assert.throws(()=>settings({WEB_PUBLIC_ORIGIN:'http://example.com',WEB_BACKEND_URL:'https://example.com'}));
  assert.throws(()=>settings({WEB_BACKEND_URL:'https://user:pass@example.com'}));
  assert.throws(()=>settings({WEB_BACKEND_URL:'https://example.com/path'}));
  assert.throws(()=>settings({HOST:'0.0.0.0',WEB_BACKEND_URL:'https://example.com'}));
  assert.equal(settings({WEB_BACKEND_URL:'https://example.com'}).upstream.origin,'https://example.com');
  assert.throws(()=>settings({WEB_BACKEND_URL:'https://example.com',WEB_PRIVATE_DEMO:'1',HOST:'0.0.0.0',WEB_PUBLIC_ORIGIN:'https://example.com'}));
  assert.throws(()=>settings({WEB_BACKEND_URL:'https://example.com',WEB_DEMO_SUBJECT_ID:'wrong/path'}));
});
test('unsafe methods require the exact browser origin before reaching the backend',async t=>{
  let calls=0;const {config}=await harness(t,(_q,r)=>{calls++;r.end('{}');});
  for(const origin of [undefined,'https://another.example']){
    const headers=origin?{Origin:origin}:{};
    assert.equal((await fetch(config.origin+'/api/v1/accounts/login',{method:'POST',headers,body:'{}'})).status,403);
  }
  assert.equal(calls,0);
  assert.equal((await fetch(config.origin+'/api/v1/accounts/login',{method:'POST',headers:{Origin:config.origin},body:'{}'})).status,200);
  assert.equal(calls,1);
});
test('proxy preserves payload and ranges, translates cookie to bearer, limits headers',async t=>{
  let observed;const {config}=await harness(t,async(q,r)=>{
    let body='';for await(const chunk of q)body+=chunk;
    observed={path:q.url,headers:q.headers,body};r.writeHead(206,{'Content-Type':'audio/wav','Content-Range':'bytes 0-3/9','Cache-Control':'public'});r.end('RIFF');
  });
  const result=await fetch(config.origin+'/api/v1/episodes?x=1',{method:'POST',headers:{Origin:config.origin,'Content-Type':'audio/wav',Cookie:'remember_session=test-session; other=private','X-Forwarded-Host':'evil.example',Range:'bytes=0-3'},body:'audio'});
  assert.equal(result.status,206);assert.equal(await result.text(),'RIFF');assert.equal(result.headers.get('cache-control'),'no-store');
  assert.equal(observed.headers.origin,undefined);assert.equal(observed.headers.cookie,undefined);assert.equal(observed.headers.authorization,'Bearer test-session');
  assert.equal(observed.headers['x-forwarded-host'],undefined);assert.equal(observed.headers.range,'bytes=0-3');assert.equal(observed.body,'audio');
});
test('demo login issues HttpOnly cookie without exposing its password or bearer in JSON',async t=>{
  let credentials;const {config}=await harness(t,async(q,r)=>{
    let raw='';for await(const part of q)raw+=part;credentials=JSON.parse(raw);
    r.writeHead(200,{'Content-Type':'application/json','Set-Cookie':'remember_session=test-token; HttpOnly; Secure; SameSite=Strict; Path=/; Domain=example.com'});
    r.end(JSON.stringify({actor_token:'test-token'}));
  });
  const response=await fetch(config.origin+'/demo/login',{method:'POST',headers:{Origin:config.origin,'Content-Type':'application/json'},body:JSON.stringify({role:'reader'})});
  assert.equal(response.status,200);assert.deepEqual(credentials,config.demo.reader);
  assert.deepEqual(await response.json(),{ok:true,role:'reader',shared_demo:true});
  assert.match(response.headers.get('set-cookie'),/HttpOnly/);assert.match(response.headers.get('set-cookie'),/SameSite=Strict/);
  assert.doesNotMatch(response.headers.get('set-cookie'),/Domain=|Secure/);
  const publicConfig=await (await fetch(config.origin+'/web-config')).text();assert.doesNotMatch(publicConfig,/test-only-password|fictional|test-token/);
});
test('unconfigured demo role, oversized body, internal paths and host spoofing are rejected',async t=>{
  let calls=0;const {config}=await harness(t,(_q,r)=>{calls++;r.end('{}');});
  assert.equal((await fetch(config.origin+'/demo/login',{method:'POST',headers:{Origin:config.origin},body:'{"role":"owner"}'})).status,404);
  assert.equal((await fetch(config.origin+'/api/v1/episodes',{method:'POST',headers:{Origin:config.origin},body:'x'.repeat(65)})).status,413);
  assert.equal((await fetch(config.origin+'/internal/secrets')).status,404);
  const status=await new Promise(r=>http.get(config.origin+'/healthz',{headers:{Host:'evil.example'}},response=>{response.resume();r(response.statusCode);}));assert.equal(status,400);
  assert.equal(calls,0);
});
test('upstream failure returns a readable error, never fixture content',async t=>{
  const {config}=await harness(t,(q)=>q.socket.destroy());
  const r=await fetch(config.origin+'/api/v1/workbench/spaces');assert.equal(r.status,502);assert.match((await r.json()).error_message,/记忆服务/);
});
test('build preserves shared JS byte-for-byte and excludes credentials from public assets',async()=>{
  const manifest=JSON.parse(await readFile(resolve(root,'dist/build-info.json')));
  for(const file of ['app.js','companion.js','narrative.js','live-garden.js']){
    const shared=await readFile(resolve(root,'../../services/backend/app/workbench',file));
    const built=await readFile(resolve(root,'dist/workbench',file));assert.deepEqual(built,shared);
  }
  for(const [name,hash] of Object.entries(manifest.files))assert.equal(createHash('sha256').update(await readFile(resolve(root,'dist',name))).digest('hex'),hash);
  assert.equal(Object.keys(manifest.files).some(n=>n.includes('.env') || n.endsWith('.pem')),false);
  const sw=await readFile(resolve(root,'dist/sw.js'),'utf8');assert.doesNotMatch(sw,/caches\.(open|match)|cache\.put/);
});
test('audio import retains its original extension and recorder blobs use their MIME',async()=>{
  const source=await readFile(resolve(root,'../../services/backend/app/workbench/app.js'),'utf8');
  const declaration=source.split('\n').find(line=>line.startsWith('function recordingName('));
  const name=vm.runInNewContext(declaration+'; recordingName;',{File});
  assert.equal(name(new File(['test'],'sample.wav',{type:'audio/wav'})),'sample.wav');
  assert.equal(name(new File(['test'],'test.mp3',{type:'audio/mpeg'})),'test.mp3');
  assert.equal(name(new Blob(['test'],{type:'audio/mp4'})),'recording.m4a');
  assert.equal(name(new Blob(['test'],{type:'audio/webm;codecs=opus'})),'recording.webm');
});
test('a late request cannot return previous identity data after a space or login switch',async()=>{
  const source=await readFile(resolve(root,'../../services/backend/app/workbench/app.js'),'utf8');
  const declaration=source.slice(source.indexOf('async function api('),source.indexOf('\nfunction on('));
  let release;const identity={epoch:0,token:'@cookie'};
  const api=vm.runInNewContext(declaration+'; api;',{state:identity,FormData,fetch:()=>new Promise(r=>release=r)});
  const pending=api('/api/v1/workbench/spaces');identity.epoch++;
  release({ok:true,json:async()=>({previous_person:'must not be shown'})});
  await assert.rejects(pending,e=>e.cancelled===true);
});
