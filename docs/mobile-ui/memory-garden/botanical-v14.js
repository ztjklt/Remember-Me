/* Original seeded botanical drawing. Nine five-lobed blooms, not 45 fabricated memories.
   Reference reasoning and source links: ../NATURE_UI_V14.md. No imported renderer. */
(function(root){
  const previous=typeof module!=='undefined'&&module.exports?require('./botanical-v13.js'):root.GardenArtwork;
  const n=v=>Number(v.toFixed(2));
  function random(seed){return()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};}
  const flowers=[
    {x:211,y:60,s:.57,r:19,tilt:.72,seed:201},
    {x:283,y:108,s:.66,r:37,tilt:.78,seed:713},
    {x:140,y:106,s:.77,r:-14,tilt:.9,seed:823},
    {x:72,y:170,s:.83,r:-31,tilt:.89,seed:135},
    {x:222,y:181,s:1.08,r:8,tilt:1,seed:341},
    {x:295,y:246,s:.72,r:29,tilt:.78,seed:961},
    {x:140,y:252,s:.93,r:-17,tilt:.91,seed:411},
    {x:61,y:299,s:.63,r:12,tilt:.66,seed:491},
    {x:229,y:324,s:.69,r:31,tilt:.75,seed:291}
  ];
  function shape(r){
    const len=49+r()*12,left=24+r()*7,right=23+r()*10,bend=(r()-.5)*11,notch=2+r()*3;
    // Each shoulder, cleft and side is independent; the shallow cleft retains the brand silhouette.
    const d=`M-3 3 C${n(-left*.65)} -8 ${n(-left-3)} ${n(-len*.4)} ${n(bend-left)} ${n(-len*.7)} C${n(bend-left-4)} ${n(-len*.95)} ${n(bend-13)} ${n(-len-6)} ${n(bend-4)} ${n(-len)} Q${n(bend)} ${n(-len+notch)} ${n(bend+4)} ${n(-len+1)} C${n(bend+18)} ${n(-len-6)} ${n(right+8)} ${n(-len*.86)} ${n(right)} ${n(-len*.64)} C${n(right-1)} ${n(-len*.33)} 17 -4 3 3Z`;
    return {d,len,bend,left,right};
  }
  function bloom(f,index){
    const r=random(f.seed),petals=[];
    for(let i=0;i<5;i++){
      const p=shape(r),id=`v14-p-${index}-${i}`,angle=n(i*72+(r()-.5)*13),hue=n(199+r()*16),sat=n(24+r()*11),light=n(66+r()*10);
      const vein=`M0 -3 Q${n(p.bend-4)} ${n(-p.len*.44)} ${n(p.bend)} ${n(-p.len*.85)}`;
      const branches=[-1,1].map(side=>Array.from({length:3},(_,j)=>{const y=-14-j*8;return `<path d="M${n(p.bend*.25)} ${y} Q${side*10} ${y-4} ${n(side*(16+j*3))} ${n(y-11)}"/>`;}).join('')).join('');
      const grain=Array.from({length:34},()=>`<circle cx="${n(-30+r()*64)}" cy="${n(-61+r()*63)}" r="${n(.12+r()*.32)}" opacity="${n(.12+r()*.22)}"/>`).join('');
      petals.push(`<g class="living-petal" transform="rotate(${angle})"><defs><radialGradient id="${id}" cx="37%" cy="22%" r="89%"><stop stop-color="hsl(${hue} ${sat}% ${light+13}%)"/><stop offset=".5" stop-color="hsl(${hue} ${sat}% ${light}%)"/><stop offset=".82" stop-color="hsl(${hue+5} ${sat}% ${light-12}%)"/><stop offset="1" stop-color="#dbe5cb"/></radialGradient><clipPath id="${id}-clip"><path d="${p.d}"/></clipPath></defs><path class="living-petal-surface" d="${p.d}" fill="url(#${id})"/><g clip-path="url(#${id}-clip)"><path class="petal-shadow" d="M-3 0 Q-6 -27 ${n(p.bend-p.left)} ${n(-p.len*.74)} Q-15 -19 2 -1Z"/><g class="living-veins">${branches}<path class="midrib" d="${vein}"/></g><path class="petal-lip" d="M${n(p.bend-p.left+2)} ${n(-p.len*.75)} Q${n(p.bend-p.left)} ${n(-p.len-1)} ${n(p.bend-5)} ${n(-p.len+1)}"/><g class="living-grain">${grain}</g></g></g>`);
    }
    const eye=Array.from({length:5},(_,i)=>`<ellipse cx="0" cy="-7" rx="4.2" ry="6.3" transform="rotate(${i*72+5})" fill="#f5e5a5"/>`).join('');
    return `<g class="living-bloom" transform="translate(${f.x} ${f.y}) rotate(${f.r}) scale(${f.s} ${n(f.s*f.tilt)})">${petals.join('')}<g class="living-eye">${eye}<circle r="6.8" fill="#d8ad58"/><circle cy=".7" r="2.8" fill="#7b6e43"/><path d="M-4 -3 Q0 -6 4 -3" stroke="#fff4ca" stroke-width="1.3" fill="none"/></g></g>`;
  }
  function leaf(x,y,angle,size,seed){
    const r=random(seed),bend=3+r()*7,len=48+r()*15,w=11+r()*7;
    const veins=Array.from({length:6},(_,i)=>{const y=-9-i*7;return `<path d="M${n(bend*.5)} ${y} Q${-w*.6} ${y-4} ${-w*.63} ${y-9} M${n(bend*.5)} ${y} Q${w*.75} ${y-4} ${w*.8} ${y-9}"/>`;}).join('');
    return `<g class="living-leaf" transform="translate(${x} ${y}) rotate(${angle}) scale(${size})"><path d="M0 0 Q${-w*1.6} ${-len*.52} ${bend} ${-len} Q${w*1.6} ${-len*.43} 0 0Z" fill="url(#v14-leaf)"/><g class="leaf-veins">${veins}<path d="M0 0 Q${bend+2} ${-len*.5} ${bend} ${-len}"/></g></g>`;
  }
  function botanical(){
    const defs='<defs><linearGradient id="v14-leaf" x1="0" y1="0" x2="1" y2=".4"><stop stop-color="#aab894"/><stop offset=".49" stop-color="#849f80"/><stop offset=".51" stop-color="#75917b"/><stop offset="1" stop-color="#a9bba0"/></linearGradient><linearGradient id="v14-stem" x1="0" y1="1" x2="1" y2="0"><stop stop-color="#597d64"/><stop offset=".5" stop-color="#91a47e"/><stop offset="1" stop-color="#bbc3a5"/></linearGradient></defs>';
    const stems=`<g class="living-stems"><path class="main-stem" d="M175 396 C211 334 188 273 207 212 C220 167 175 145 184 115 Q183 87 211 60"/><path d="M193 343 Q235 354 229 324 M191 333 Q110 365 61 299 M193 303 Q167 282 140 252 M204 247 Q282 289 295 246 M204 226 Q106 259 72 170 M202 184 Q250 180 283 108 M187 145 Q156 145 140 106 M207 212 Q218 202 222 181 M184 115 Q230 78 258 58"/></g>`;
    const leaves=leaf(192,357,-52,.94,18)+leaf(195,307,55,.86,12)+leaf(204,248,66,.66,92)+leaf(109,231,-49,.55,81)+leaf(242,160,37,.55,85)+leaf(183,136,-46,.41,98);
    const buds='<g class="living-buds" transform="translate(258 58) rotate(32)"><path d="M0 0 Q-10 -6 -5 -14 Q5 -20 8 -10 Q10 -4 0 0" fill="#a49fb2"/><path d="M-1 2 L-8 -8 L0 -4 L6 -11 L5 0Z" fill="#91a58b"/><path d="M-3 -13 Q0 -16 4 -13" stroke="#d9ced7" fill="none"/></g>';
    return defs+stems+leaves+buds+flowers.map(bloom).join('');
  }
  const drawing=botanical();
  const api={bloom,render:layout=>layout==='constellation'?previous.render(layout):drawing};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.GardenArtwork=api;
})(typeof window==='undefined'?{}:window);
