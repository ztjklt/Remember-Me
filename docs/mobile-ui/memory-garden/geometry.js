/* Camera positions use the same 360 × 400 world coordinates at every viewport. */
(function(root){
  const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
  function constrain(camera){
    const z=clamp(camera.z,1,2.8),limitX=(z-1)*180,limitY=(z-1)*200;
    return {z,x:clamp(camera.x,-limitX,limitX)||0,y:clamp(camera.y,-limitY,limitY)||0};
  }
  function zoomAt(camera,zoom,anchor={x:180,y:200}){
    const z=clamp(zoom,1,2.8),ratio=z/camera.z;
    return constrain({z,x:anchor.x-180-(anchor.x-180-camera.x)*ratio,y:anchor.y-200-(anchor.y-200-camera.y)*ratio});
  }
  function pinch(camera,start,end){
    const dist=p=>Math.hypot(p[0].x-p[1].x,p[0].y-p[1].y);
    const mid=p=>({x:(p[0].x+p[1].x)/2,y:(p[0].y+p[1].y)/2});
    const a=mid(start),b=mid(end),z=clamp(camera.z*dist(end)/Math.max(dist(start),1),1,2.8),r=z/camera.z;
    return constrain({z,x:b.x-180-(a.x-180-camera.x)*r,y:b.y-200-(a.y-200-camera.y)*r});
  }
  function point(index,layout='flower'){
    if(layout==='constellation'){
      // Broad irregular rows retain usable touch spacing at 320px, without a flower outline.
      const positions=[[58,55],[149,35],[255,55],[319,112],[229,131],[123,111],[37,153],[83,220],[176,208],[290,219],[320,295],[227,311],[129,301],[37,329],[170,367]];
      return {x:positions[index][0],y:positions[index][1]};
    }
    // Stable positions along nine blooms; reserve 48px circular touch targets at 320px.
    const positions=[[211,48],[135,88],[284,95],[68,151],[155,163],[232,157],
      [310,220],[240,243],[159,238],[88,223],[43,288],[120,309],
      [208,316],[285,321],[327,155]];
    return {x:positions[index][0],y:positions[index][1]};
  }
  // Bound each branch to 15 touch targets. Appending memories never moves existing slots;
  // filtering hides empty branches without re-packing the remaining points.
  function branches(points,matches=()=>true){
    const groups=new Map();
    points.forEach((p,i)=>{if(!matches(p))return;const id=Math.floor(i/15);
      if(!groups.has(id))groups.set(id,{id,points:[]});
      groups.get(id).points.push({...p,layoutIndex:i%15});
    });
    return [...groups.values()];
  }
  function storyEdges(points,layout='flower'){
    const edges=[];
    for(const episode of new Set(points.map(p=>p.episode))){
      const pending=points.filter(p=>p.episode===episode).map(p=>({...p,...point(p.layoutIndex,layout)}));
      if(!pending.length)continue;
      const tree=[pending.shift()];
      while(pending.length){
        let best;
        tree.forEach(a=>pending.forEach((b,i)=>{const d=Math.hypot(a.x-b.x,a.y-b.y);if(!best||d<best.d)best={a,b,i,d};}));
        edges.push({episode,from:best.a.id,to:best.b.id,a:best.a,b:best.b});
        tree.push(pending.splice(best.i,1)[0]);
      }
    }
    return edges;
  }
  const api={constrain,zoomAt,pinch,point,storyEdges,branches};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.GardenGeometry=api;
})(typeof window==='undefined'?{}:window);
