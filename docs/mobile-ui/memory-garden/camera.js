/* A single camera for a stable 360 x 420 botanical world.
   Interpolate the focus in screen space and zoom logarithmically: no retreat,
   spring, independent object flight, or CSS matrix decomposition. */
(function(root){
  const center={x:180,y:210};
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const project=(p,c)=>({x:180+(p.x-180)*c.z+c.x,y:210+(p.y-210)*c.z+c.y});
  const unproject=(p,c)=>({x:180+(p.x-180-c.x)/c.z,y:210+(p.y-210-c.y)/c.z});
  const focus=(p,z)=>({x:(180-p.x)*z,y:(210-p.y)*z,z});
  const duration=620;
  const timing=t=>({focus:1-Math.pow(1-clamp(t,0,1),5),zoom:1-Math.pow(1-clamp(t,0,1),3)});
  function interpolate(from,to,anchor){
    const a=project(anchor,from),b=project(anchor,to);
    return progress=>{
      if(progress<=0)return {...from};if(progress>=1)return {...to};
      // Quintic ease-out responds at once and arrives with zero velocity/acceleration.
      // Pan settles a little earlier than magnification, without ever reversing.
      const {focus:p,zoom:s}=timing(progress);
      const z=Math.exp(Math.log(from.z)+(Math.log(to.z)-Math.log(from.z))*s);
      return {z,x:a.x+(b.x-a.x)*p-180-(anchor.x-180)*z,y:a.y+(b.y-a.y)*p-210-(anchor.y-210)*z};
    };
  }
  function constrain(c){const z=clamp(c.z,1,4.8);return{z,x:clamp(c.x,-360*z,360*z),y:clamp(c.y,-420*z,420*z)};}
  function zoomAt(c,z,p=center){z=clamp(z,1,4.8);const w=unproject(p,c);return constrain({z,x:p.x-180-(w.x-180)*z,y:p.y-210-(w.y-210)*z});}
  function pinch(c,start,end){
    const mid=p=>({x:(p[0].x+p[1].x)/2,y:(p[0].y+p[1].y)/2});
    const dist=p=>Math.hypot(p[0].x-p[1].x,p[0].y-p[1].y),a=mid(start),b=mid(end),w=unproject(a,c);
    const z=clamp(c.z*dist(end)/Math.max(dist(start),1),1,4.8);
    return constrain({z,x:b.x-180-(w.x-180)*z,y:b.y-210-(w.y-210)*z});
  }
  const api={center,project,unproject,focus,interpolate,constrain,zoomAt,pinch,duration,timing};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.GardenCamera=api;
})(typeof window==='undefined'?{}:window);
