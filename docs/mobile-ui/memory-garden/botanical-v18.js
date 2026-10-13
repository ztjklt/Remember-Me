/* Gently winding herbaceous sprigs. Every offshoot grows from the same sampled
   stem, and the flowering tip stays attached to its stable world coordinate. */
(function(root){
  const previous=typeof module!=='undefined'&&module.exports?require('./botanical-v17.js'):root.GardenArtwork;
  const n=v=>Number(v.toFixed(3)),esc=s=>String(s).replaceAll('&','&amp;').replaceAll('"','&quot;');
  function line(points){return points.map((p,i)=>`${i?'L':'M'}${n(p.x)} ${n(p.y)}`).join(' ');}
  function ribbon(at,width){
    const left=[],right=[];
    for(let i=0;i<=64;i++){const t=i/64,p=at(t),a=at(Math.max(0,t-.001)),b=at(Math.min(1,t+.001)),dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1,w=width(t);
      left.push({x:p.x-dy/d*w,y:p.y+dx/d*w});right.push({x:p.x+dy/d*w,y:p.y-dx/d*w});}
    return `${line(left)} ${line(right.reverse()).replace('M','L')}Z`;
  }
  function leaf(p,angle,length,width){return `<g class="sprig-leaf" transform="translate(${n(p.x)} ${n(p.y)}) rotate(${n(angle)})"><path fill="url(#v18-leaf)" d="M0 0 C${n(-width)} ${n(-length*.18)} ${n(-width*.84)} ${n(-length*.72)} 4 ${n(-length)} C${n(width*.9)} ${n(-length*.55)} ${n(width*.66)} ${n(-length*.13)} 0 0Z"/><path class="sprig-leaf-fold" d="M0 0 Q5 ${n(-length*.44)} 4 ${n(-length)}"/><path class="sprig-leaf-veins" d="M2 ${n(-length*.28)} l${n(-width*.53)} ${n(-length*.18)} M3 ${n(-length*.48)} l${n(width*.38)} ${n(-length*.17)}"/></g>`;}
  function foliage(flowers){
    return `<svg class="depth-stems" viewBox="0 0 360 420" aria-hidden="true"><defs><linearGradient id="v18-stem"><stop stop-color="#627f61"/><stop offset=".34" stop-color="#829868"/><stop offset=".63" stop-color="#b2bc89"/><stop offset="1" stop-color="#668460"/></linearGradient><linearGradient id="v18-leaf" x2=".8" y2=".3"><stop stop-color="#b6c29d"/><stop offset=".48" stop-color="#8da480"/><stop offset=".5" stop-color="#789671"/><stop offset="1" stop-color="#a4b68b"/></linearGradient><linearGradient id="v18-bud"><stop stop-color="#bbc2a0"/><stop offset="1" stop-color="#829883"/></linearGradient></defs>${flowers.map((f,i)=>{
      const base=154+i*22,side=i===1?-1:1,bend=[23,-27,25][i%3];
      // An S curve with a broad middle bend, never a uniform sine coil.
      const at=t=>({x:base+(f.x-base)*t+bend*Math.sin(Math.PI*2*t)*Math.sin(Math.PI*t)+side*8*Math.sin(Math.PI*t),y:441+(f.y-441)*t});
      const path=ribbon(at,t=>2.45*(1-t)+.82),spine=Array.from({length:65},(_,k)=>at(k/64));
      const leaves=[.21,.42,.63].map((t,j)=>{const p=at(t),dir=j%2?-1:1,angle=dir*(35+(f.seed+j*7)%15);return `<ellipse class="sprig-node" cx="${n(p.x)}" cy="${n(p.y)}" rx="2.7" ry="1.5" transform="rotate(${angle/2} ${n(p.x)} ${n(p.y)})"/>${leaf(p,angle,42-j*6+(f.seed%7),9.2-j*1.25)}`;}).join('');
      const origin=at(.51),bud={x:origin.x+side*36,y:origin.y-49},twig=`M${n(origin.x)} ${n(origin.y)} C${n(origin.x+side*26)} ${n(origin.y-8)} ${n(bud.x+side*12)} ${n(bud.y+14)} ${n(bud.x)} ${n(bud.y)}`;
      return `<g class="depth-sprig" data-sprig="${esc(f.id)}"><path class="sprig-stalk" fill="url(#v18-stem)" d="${path}"/><path class="sprig-stem-light" d="${line(spine)}"/><path d="${twig}" fill="none" stroke="#84986c" stroke-width="1.45"/><g transform="translate(${n(bud.x)} ${n(bud.y)}) rotate(${side*24})"><path class="sprig-bud" fill="url(#v18-bud)" d="M0 4 C-7 1-6-10-1-12 C5-12 7-1 0 4Z"/><path d="M0 4 Q-1-4 0-9" fill="none" stroke="#dce1bb" stroke-width=".5"/></g>${leaves}<path class="sprig-calyx" d="M${n(f.x-6)} ${n(f.y+9)} L${n(f.x-8)} ${n(f.y-3)} L${n(f.x)} ${n(f.y+1)} L${n(f.x+6)} ${n(f.y-4)} L${n(f.x+5)} ${n(f.y+8)}Z"/></g>`;
    }).join('')}</svg>`;
  }
  const api={...previous,foliage};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.GardenArtwork=api;
})(typeof window==='undefined'?{}:window);
