import {mkdir, readFile, writeFile, readdir, copyFile} from 'node:fs/promises';
import {resolve, dirname, relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
const dist = resolve(here, 'dist');
const sha = data => createHash('sha256').update(data).digest('hex');
const source = 'services/backend/app/workbench';
const names = (await readdir(resolve(root, source))).filter(n => /\.(html|js|css|svg)$/.test(n));
const assets = ['v2/svg/mark-light.svg', 'v20/bloom-side.png', 'v20/bloom-cupped.png', 'v21/stem.png'];
const inputs = [...names.map(n => `${source}/${n}`), ...assets.map(n => `assets/brand/forget-me-not/${n}`),
  'apps/android/app/src/main/res/drawable-nodpi/rm_brand_foreground.png'];
const overlays = (await readdir(resolve(here, 'shell'))).sort();
const clientFiles = (await readdir(resolve(here, 'client'))).sort();
const androidRoot = 'apps/android/app/src/main/java/me/remember/app/integration';
const nativeSources = ['MemoryMap.kt','GardenProjection.kt','MemoryGardenScreen.kt','NarrativeScreen.kt'].map(n => `${androidRoot}/${n}`);
const nativeAssets = ['rm_garden_flower_front','rm_garden_flower_side','rm_garden_flower_cupped','rm_garden_stem','rm_garden_vine','rm_garden_path'];
const assetRoot = 'apps/android/app/src/main/res/drawable-nodpi';
inputs.push(...clientFiles.map(n => `apps/web/client/${n}`),...nativeSources,...nativeAssets.map(n => `${assetRoot}/${n}.png`));
inputs.push(...overlays.map(n => `apps/web/shell/${n}`), 'apps/web/build.mjs');
inputs.push('apps/web/native-compat.json');
const hashes = Object.fromEntries(await Promise.all(inputs.map(async name => [name, sha(await readFile(resolve(root, name)))])));
const compatibility=JSON.parse(await readFile(resolve(here,'native-compat.json'),'utf8'));
for (const [name,expected] of Object.entries(compatibility.sources)) {
  if(hashes[name]!==expected)throw Error(`Android projection changed: ${name}. Compare client/model.js and its isolation tests before updating native-compat.json.`);
}
if (process.argv.includes('--check')) {
  const saved = JSON.parse(await readFile(resolve(dist, 'build-info.json')));
  const changed = Object.keys(hashes).filter(name => hashes[name] !== saved.sources[name]);
  const removed = Object.keys(saved.sources).filter(name => !(name in hashes));
  if (changed.length || removed.length) {
    console.error('Web build needs refreshing:', [...changed, ...removed].join('\n'));
    process.exitCode = 1;
  } else console.log('Web assets match current shared workbench and shell.');
} else {
  await mkdir(resolve(dist, 'workbench'), {recursive:true});
  await mkdir(resolve(dist, 'app/assets'), {recursive:true});
  for (const name of clientFiles) await copyFile(resolve(here,'client',name),resolve(dist,'app',name));
  for (const name of nativeAssets) await copyFile(resolve(root,assetRoot,name+'.png'),resolve(dist,'app/assets',name+'.png'));
  // Display vocabulary follows Android source; fail rather than silently drift.
  const map = await readFile(resolve(root,androidRoot,'MemoryMap.kt'),'utf8');
  const facetsBlock = map.match(/val memorySideTitles = linkedMapOf\(([\s\S]*?)\)\s*val personViewTitles/);
  const viewsBlock = map.match(/val personViewTitles = listOf\(([^\n]+)\)/);
  const viewSets = map.match(/val narrativeViewFacets = listOf\(([\s\S]*?)\n\)/);
  if(!facetsBlock || !viewsBlock || !viewSets) throw Error('Android memory vocabulary changed; review the Web adapter.');
  const facetTitles=Object.fromEntries([...facetsBlock[1].matchAll(/"([A-Z_]+)" to "([^"]+)"/g)].map(m=>[m[1],m[2]]));
  const viewTitles=[...viewsBlock[1].matchAll(/"([^"]+)"/g)].map(m=>m[1]);
  const viewFacets=[...viewSets[1].matchAll(/setOf\(([^)]+)\)/g)].map(m=>[...m[1].matchAll(/"([^"]+)"/g)].map(x=>x[1]));
  if(Object.keys(facetTitles).length!==8 || viewTitles.length!==4 || viewFacets.length!==4)throw Error('Review changed Android view/facet counts.');
  await writeFile(resolve(dist,'app/native-labels.js'),`// Generated from Android MemoryMap.kt. Do not edit.\nexport const facetTitles=${JSON.stringify(facetTitles)};\nexport const viewTitles=${JSON.stringify(viewTitles)};\nexport const viewFacets=${JSON.stringify(viewFacets)};\n`);
  const shell = '<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#edf1e7"><meta name="apple-mobile-web-app-capable" content="yes"><link rel="apple-touch-icon" href="/icon.png"><link rel="stylesheet" href="/shell.css"><script src="/shell.js" defer></script>';
  for (const name of names) {
    let data = await readFile(resolve(root, source, name));
    if (name.endsWith('.html')) {
      let text = data.toString().replace('</head>', shell + '</head>').replace('width=device-width, initial-scale=1', 'width=device-width, initial-scale=1, viewport-fit=cover');
      if (name === 'index.html') {
        const start = text.indexOf('<section id="login">');
        const end = text.indexOf('<section id="workspace"');
        if (start < 0 || end < 0) throw Error('Shared login markup changed; review the shell adapter before building.');
        text = text.slice(0, start) + await readFile(resolve(here, 'shell/login.html'), 'utf8') + '\n' + text.slice(end);
        text = text.replace('<title>勿忘我 · 真实记忆工作台</title>', '<title>勿忘我 · 留下故事，慢慢了解</title>');
        text = text.replace('<body>', '<body class="capture-app">').replace('人物与亲友补记</a>', '陪伴与亲友</a>');
        text = text.replace('<p id="capabilities" class="muted"></p>', '<details class="connection-details"><summary>连接状态</summary><p id="capabilities" class="muted"></p></details>');
      } else if (name === 'companion.html') {
        text = text.replace('<body>', '<body class="companion-app">');
        text = text.replace('注册账号或回到记录工作台', '回到首页，选择体验身份或登录');
      }
      data = Buffer.from(text);
    }
    await writeFile(resolve(dist, 'workbench', name), data);
  }
  for (const name of assets) {
    const target = resolve(dist, 'brand', name);
    await mkdir(dirname(target), {recursive:true});
    await copyFile(resolve(root, 'assets/brand/forget-me-not', name), target);
  }
  await copyFile(resolve(root, 'apps/android/app/src/main/res/drawable-nodpi/rm_brand_foreground.png'), resolve(dist, 'icon.png'));
  for (const name of overlays.filter(n => n !== 'login.html')) await copyFile(resolve(here, 'shell', name), resolve(dist, name));
  let commit = 'unavailable';
  try { commit = execFileSync('git', ['rev-parse', 'HEAD'], {cwd:root, encoding:'utf8'}).trim(); } catch {}
  const files = {};
  async function record(dir) {
    for (const item of await readdir(dir, {withFileTypes:true})) {
      const path = resolve(dir, item.name);
      if (item.isDirectory()) await record(path);
      else if(item.name !== 'build-info.json') files[relative(dist, path).replaceAll('\\', '/')] = sha(await readFile(path));
    }
  }
  await record(dist);
  await writeFile(resolve(dist, 'build-info.json'), JSON.stringify({client:'remember-me-web',version:'0.2.0',commit,built_at:new Date().toISOString(),sources:hashes,files}, null, 2));
  console.log(`Built ${Object.keys(files).length} assets from shared workbench at ${commit.slice(0, 12)}.`);
}
