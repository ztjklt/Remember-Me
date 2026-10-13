/* One scene plane, one camera. All lengths are CSS pixels except camera x/y. */
(function(root){
  const scenes=[{id:'pond',name:'池畔薄暮',src:'nature/garden-v20/pond.png'},{id:'path',name:'暖色花径',src:'nature/garden-v20/path.png'},{id:'woodland',name:'林间微光',src:'nature/garden-v20/woodland.png'},{id:'night',name:'月下花园',src:'nature/garden-v21/night.png'}];
  const next=(previous,random=Math.random)=>{const pool=scenes.filter(s=>s.id!==previous);return pool[Math.min(pool.length-1,Math.max(0,Math.floor(random()*pool.length)))].id;};
  const metrics=(stage,scene)=>({sx:stage.width/360,sy:stage.height/420,ox:stage.left-scene.left+stage.width/2,oy:stage.top-scene.top+stage.height/2,w:scene.width,h:scene.height});
  const css=(c,m)=>`translate3d(${c.x*m.sx}px,${c.y*m.sy}px,0) scale(${c.z})`;
  function constrain(c,m){
    if(!m)return c;const z=Math.max(1,Math.min(4.8,c.z)),pad=27;
    const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
    return{z,x:clamp(c.x,((1-z)*(m.w-m.ox)-pad*z)/m.sx,((z-1)*m.ox+pad*z)/m.sx),y:clamp(c.y,((1-z)*(m.h-m.oy)-pad*z)/m.sy,((z-1)*m.oy+pad*z)/m.sy)};
  }
  const api={scenes,next,metrics,css,constrain};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.GardenSceneModel=api;
})(typeof window==='undefined'?{}:window);
