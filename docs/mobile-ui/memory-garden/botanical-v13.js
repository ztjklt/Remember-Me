/* Original procedural illustration, derived from the repository's v2 petal silhouette.
   Fine stipples are decorative and never represent additional stored memories. */
(function(root){
  const petal=[[-2,3],[-16,-6,-34,-22,-34,-42],[-34,-60,-21,-71,-7,-69],[-3,-69,0,-67,3,-66],[17,-71,31,-64,34,-51],[40,-29,20,-6,4,3]];
  const path='M'+petal[0].join(' ')+petal.slice(1).map(c=>'C'+c.join(' ')).join('')+'Z';
  const n=v=>Number(v.toFixed(2));
  function random(seed){return ()=>{seed=(Math.imul(1664525,seed)+1013904223)>>>0;return seed/4294967296;};}
  function contour(){
    const vertices=[petal[0]];let from=petal[0];
    for(const c of petal.slice(1)){
      for(let i=1;i<=16;i++){const t=i/16,s=1-t;vertices.push([s*s*s*from[0]+3*s*s*t*c[0]+3*s*t*t*c[2]+t*t*t*c[4],s*s*s*from[1]+3*s*s*t*c[1]+3*s*t*t*c[3]+t*t*t*c[5]]);}
      from=c.slice(4);
    }
    return vertices;
  }
  const polygon=contour();
  function inside(x,y){let yes=false;for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){
    const a=polygon[i],b=polygon[j];if((a[1]>y)!==(b[1]>y)&&x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])yes=!yes;
  }return yes;}
  function stipples(count,seed){
    const r=random(seed),dots=[];let tries=0;
    while(dots.length<count&&tries++<count*30){const x=-35+r()*73,y=-71+r()*75;if(!inside(x,y))continue;
      dots.push(`<circle class="petal-grain" cx="${n(x)}" cy="${n(y)}" r="${n(.24+r()*.65)}" opacity="${n(.2+r()*.5)}"/>`);
    }
    return dots.join('');
  }
  function bloom(x,y,scale,rotation,count,seed){
    const petals=Array.from({length:5},(_,i)=>`<g transform="rotate(${i*72+[-4,3,-2,4,0][i]}) scale(${[1,.93,1.02,.98,1.04][i]} ${[1,1.04,.94,1.03,.97][i]})"><path class="botanical-petal" d="${path}" fill="url(#botanical-petal-${i%3})"/><path class="botanical-fold" d="M0 0 C-6 -17 -4 -39 2 -60 M0 -5 Q-18 -22 -21 -43 M2 -8 Q22 -28 22 -45"/>${stipples(count,seed+i*21)}</g>`).join('');
    return `<g class="botanical-bloom" transform="translate(${x} ${y}) rotate(${rotation}) scale(${scale})">${petals}<path class="botanical-eye" d="M-3 -10 Q3 -14 8 -8 Q15 -5 10 2 Q11 10 4 10 Q-2 15 -6 8 Q-15 7 -11 0 Q-14 -7 -3 -10Z"/><circle class="botanical-gold" r="5.8"/><circle fill="#645e3f" r="1.8"/>${Array.from({length:9},(_,i)=>{const a=i*Math.PI*2/9;return `<circle cx="${n(Math.cos(a)*7.5)}" cy="${n(Math.sin(a)*7.5)}" r=".65" fill="#fff5cf"/>`;}).join('')}</g>`;
  }
  function botanical(){
    const defs=`<defs>${['#adc6d3','#99b9c8','#b7cbd6'].map((c,i)=>`<radialGradient id="botanical-petal-${i}" cx="52%" cy="76%" r="85%"><stop stop-color="#c4d2c8" stop-opacity=".9"/><stop offset=".38" stop-color="${c}" stop-opacity=".78"/><stop offset=".82" stop-color="${c}" stop-opacity=".94"/><stop offset="1" stop-color="#edf1e9" stop-opacity=".7"/></radialGradient>`).join('')}<linearGradient id="botanical-leaf" x2="1" y2="1"><stop stop-color="#b6c3a0" stop-opacity=".7"/><stop offset="1" stop-color="#719584" stop-opacity=".8"/></linearGradient></defs>`;
    const branch=`<g class="botanical-branch"><path class="botanical-stem" d="M142 374 C237 327 218 260 180 187 M191 338 C151 347 109 336 80 306 M211 287 Q257 297 281 274 M205 289 Q307 209 295 80"/><path class="botanical-leaf" d="M201 325 C226 285 259 309 280 281 C270 322 238 339 201 325Z"/><path class="botanical-leaf" d="M202 291 C165 290 156 274 135 260 C169 256 196 264 202 291Z"/><path class="botanical-leaf" d="M273 211 Q283 173 308 171 Q313 201 273 211Z"/><path class="botanical-leaf-vein" d="M201 325 Q241 318 270 290 M202 291 L144 265 M273 211 L303 177"/></g>`;
    return defs+branch+bloom(80,306,.63,-23,18,210)+bloom(295,61,.62,22,16,330)+bloom(177,175,1.94,-9,92,13);
  }
  function constellation(){
    const r=random(417),stars=[];
    for(let i=0;i<330;i++){const x=24+r()*312,y=28+r()*328;stars.push(`<circle class="constellation-grain" cx="${n(x)}" cy="${n(y)}" r="${n(.25+r()*.85)}" opacity="${n(.14+r()*.52)}"/>`);}
    return `<g class="constellation-art"><path class="constellation-trail" d="M38 281 C73 142 286 348 309 163 C320 49 189 25 91 68"/>${stars.join('')}</g>`;
  }
  const cache={flower:botanical(),constellation:constellation()};
  const api={render:layout=>cache[layout]||cache.flower};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.GardenArtwork=api;
})(typeof window==='undefined'?{}:window);
