/* Photographic stalks, calibrated from tip to base. A similarity transform
   preserves leaf proportions and circular stem shading at every flower pose. */
(function(root){
  const photo={width:1024,height:1536,tip:{x:530,y:40},base:{x:525,y:1490}};
  function fit(from,to,mirror=false){
    const p=mirror?{x:photo.width-photo.tip.x,y:photo.tip.y}:photo.tip,q=mirror?{x:photo.width-photo.base.x,y:photo.base.y}:photo.base;
    const ux=q.x-p.x,uy=q.y-p.y,vx=to.x-from.x,vy=to.y-from.y,d=ux*ux+uy*uy;
    const a=(ux*vx+uy*vy)/d,b=(ux*vy-uy*vx)/d;return{a,b,c:-b,d:a,e:from.x-a*p.x+b*p.y,f:from.y-b*p.x-a*p.y};
  }
  function foliage(flowers){return `<svg class="depth-stems" viewBox="0 0 360 420" aria-hidden="true">${flowers.map((f,i)=>{
    const mirror=i%2===1,to={x:[176,122,248][i%3],y:478},m=fit(f,to,mirror),n=v=>Number(v.toFixed(6));
    return `<g class="depth-sprig" data-sprig="${f.id}" data-stem-tip="${f.x},${f.y}" transform="matrix(${[m.a,m.b,m.c,m.d,m.e,m.f].map(n).join(' ')})"><image class="stem-photo" href="../../assets/brand/forget-me-not/v21/stem.png" width="${photo.width}" height="${photo.height}" ${mirror?`transform="translate(${photo.width} 0) scale(-1 1)"`:''}/></g>`;
  }).join('')}</svg>`;}
  const api={photo,fit,foliage};if(typeof module!=='undefined'&&module.exports)module.exports=api;else{root.GardenStemArtwork=api;root.GardenArtwork={...root.GardenArtwork,foliage};}
})(typeof window==='undefined'?{}:window);
