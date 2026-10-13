/* Original botanical drawing, informed by the project's Myosotis photo.
   Five irregular corolla lobes, a small yellow throat, and slender connected sprigs.
   No filters, particle timers, external renderer, or new memory records. */
(function(root){
  const previous=typeof module!=='undefined'&&module.exports?require('./botanical-v14.js'):root.GardenArtwork;
  const n=v=>Number(v.toFixed(3));
  const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;');
  const random=seed=>()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
  function dots(r,count,w,h){return Array.from({length:count},()=>{const x=n((r()-.5)*w),y=n(-r()*h),radius=n(.12+r()*.17);return `M${x} ${y}a${radius} ${radius} 0 1 0 ${radius*2} 0a${radius} ${radius} 0 1 0 ${-radius*2} 0`;}).join('');}
  function bloom(f,index){
    const r=random(f.seed),id=`v17-${index}`,petals=[];
    for(let i=0;i<5;i++){
      const length=52+r()*8,left=28+r()*5,right=27+r()*6,bend=(r()-.5)*7,angle=i*72+(r()-.5)*6;
      const d=`M-7 -1 C-17 -12 ${n(-left-1)} ${n(-length*.35)} ${n(bend-left)} ${n(-length*.66)} C${n(bend-left-2)} ${n(-length*.91)} ${n(bend-17)} ${n(-length-2)} ${n(bend-5)} ${n(-length)} Q${n(bend)} ${n(-length+2+r()*1.3)} ${n(bend+6)} ${n(-length-.4)} C${n(bend+22)} ${n(-length-1.4)} ${n(right+3)} ${n(-length*.89)} ${n(right)} ${n(-length*.63)} C${n(right-2)} -17 16 -7 7 1Z`;
      const hue=207+r()*7,light=68+r()*4,pid=`${id}-${i}`;
      const veins=[-1,0,1].map(side=>`M${side*4} -7 C${side*7} -19 ${n(side*14+bend*.4)} ${n(-length*.52)} ${n(side*19+bend)} ${n(-length*.85)}`).join(' ');
      petals.push(`<g class="living-petal" transform="rotate(${n(angle)})"><defs><radialGradient id="${pid}" cx="35%" cy="26%" r="86%"><stop stop-color="hsl(${n(hue)} 32% ${n(light+14)}%)"/><stop offset=".52" stop-color="hsl(${n(hue)} 34% ${n(light+3)}%)"/><stop offset=".88" stop-color="hsl(${n(hue+3)} 30% ${n(light-5)}%)"/><stop offset="1" stop-color="#e4e7cd"/></radialGradient><clipPath id="${pid}-clip"><path d="${d}"/></clipPath></defs><path class="living-petal-surface" d="${d}" fill="url(#${pid})"/><g clip-path="url(#${pid}-clip)"><path class="petal-fold" d="M-7 -1 Q-19 -17 ${n(bend-left)} ${n(-length*.68)} Q-21 -25 -3 -2Z"/><path class="petal-fibres" d="${veins}"/><path class="petal-satin" d="M${n(bend-left+1)} ${n(-length*.7)} C${n(bend-left)} ${n(-length*.89)} ${n(bend-17)} ${n(-length-.6)} ${n(bend-6)} ${n(-length+.4)}"/><path class="petal-dust" d="${dots(r,25,66,length)}"/><path class="petal-throat" d="M-7 1 Q-7 -10 -12 -18 Q-2 -12 5 -2Z"/></g></g>`);
    }
    // The yellow eye is a small continuous ring, rather than a second flower.
    const ring=Array.from({length:65},(_,i)=>{const a=i/64*Math.PI*2,rad=8.6+.6*Math.cos(a*5);return `${i?'L':'M'}${n(Math.cos(a)*rad)} ${n(Math.sin(a)*rad)}`;}).join(' ');
    return `<g class="living-bloom botanical-v17" transform="translate(${f.x} ${f.y}) rotate(${f.r}) scale(${f.s} ${n(f.s*f.tilt)})">${petals.join('')}<defs><radialGradient id="${id}-eye" cx="36%" cy="27%"><stop stop-color="#f8e7a6"/><stop offset=".68" stop-color="#e7c775"/><stop offset="1" stop-color="#c79c50"/></radialGradient></defs><g class="botanical-eye"><path d="${ring}Z" fill="url(#${id}-eye)"/><path d="M-3 -2 Q-.5 -4 2.5 -2.5 L3.2 .4 Q1.8 3.4 -1 2.8 L-3.1 .7Z" fill="#776647"/><path d="M-5.7 -3 Q-3.5 -6.6 -.8 -6.1" fill="none" stroke="#fff5ce" stroke-width=".7" stroke-linecap="round"/><circle cx=".3" cy=".6" r="1.05" fill="#d2b275"/></g></g>`;
  }
  const point=(p,t)=>{const u=1-t;return{x:u*u*u*p[0].x+3*u*u*t*p[1].x+3*u*t*t*p[2].x+t*t*t*p[3].x,y:u*u*u*p[0].y+3*u*u*t*p[1].y+3*u*t*t*p[2].y+t*t*t*p[3].y};};
  function stem(p){
    const sides=[[],[]];
    for(let i=0;i<=24;i++){
      const t=i/24,a=point(p,t),b=point(p,Math.min(1,t+.002)),c=point(p,Math.max(0,t-.002));
      const dx=b.x-c.x,dy=b.y-c.y,l=Math.hypot(dx,dy)||1,w=1.25*(1-t)+.42;
      sides[0].push(`${n(a.x-dy/l*w)} ${n(a.y+dx/l*w)}`);sides[1].push(`${n(a.x+dy/l*w)} ${n(a.y-dx/l*w)}`);
    }
    return `M${sides[0].join('L')}L${sides[1].reverse().join('L')}Z`;
  }
  function leaf(x,y,angle,length,width){
    return `<g class="sprig-leaf" transform="translate(${n(x)} ${n(y)}) rotate(${angle})"><path d="M0 0 C${-width} ${n(-length*.24)} ${n(-width*.8)} ${n(-length*.69)} 3 ${-length} C${n(width*.9)} ${n(-length*.62)} ${width} ${n(-length*.22)} 0 0Z" fill="url(#v17-leaf)"/><path class="sprig-leaf-fold" d="M0 0 Q4 ${n(-length*.46)} 3 ${-length}"/><path class="sprig-leaf-veins" d="M1 ${n(-length*.24)} l${n(-width*.48)} ${n(-length*.15)} M2 ${n(-length*.45)} l${n(width*.43)} ${n(-length*.17)} M2 ${n(-length*.61)} l${n(-width*.3)} ${n(-length*.13)}"/></g>`;
  }
  function foliage(flowers){
    const defs=`<defs><linearGradient id="v17-stalk" x1="0" y1="0" x2="1" y2=".15"><stop stop-color="#80917a"/><stop offset=".48" stop-color="#8fa083"/><stop offset="1" stop-color="#c2c9a4"/></linearGradient><linearGradient id="v17-leaf" x1="0" y1="0" x2="1" y2=".3"><stop stop-color="#b5c2a0"/><stop offset=".46" stop-color="#94aa8d"/><stop offset=".5" stop-color="#819b83"/><stop offset="1" stop-color="#a8b79a"/></linearGradient></defs>`;
    return `<svg class="depth-stems" viewBox="0 0 360 420" aria-hidden="true">${defs}${flowers.map((f,i)=>{
      const r=random(f.seed),rootX=164+i*12,side=f.x<165?-1:1;
      const p=[{x:rootX,y:444},{x:rootX+side*17,y:357},{x:f.x-side*13,y:f.y+65},{x:f.x,y:f.y}];
      const a=point(p,.26),b=point(p,.52),c=point(p,.71),path=stem(p);
      return `<g class="depth-sprig" data-sprig="${esc(f.id)}"><path class="sprig-stalk" d="${path}" fill="url(#v17-stalk)"/><path class="sprig-seam" d="M${p[0].x} ${p[0].y} C${p[1].x} ${p[1].y} ${p[2].x} ${p[2].y} ${p[3].x} ${p[3].y}"/>${leaf(a.x,a.y,-38+i*7,40+r()*9,8)}${leaf(b.x,b.y,37-i*7,32+r()*7,6.8)}${leaf(c.x,c.y,-25+i*10,21+r()*5,4.6)}<path class="sprig-calyx" d="M${n(f.x-5)} ${n(f.y+8)} L${n(f.x-8)} ${n(f.y-3)} L${n(f.x-1)} ${n(f.y+1)} L${n(f.x+5)} ${n(f.y-6)} L${n(f.x+5)} ${n(f.y+8)}Z"/></g>`;
    }).join('')}</svg>`;
  }
  const api={...previous,bloom,foliage};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.GardenArtwork=api;
})(typeof window==='undefined'?{}:window);
