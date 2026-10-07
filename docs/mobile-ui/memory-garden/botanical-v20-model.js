/* Image-space anchors keep the photographed stalk, labels and camera aligned. */
(function(root){
  const poses={
    cupped:{file:'bloom-cupped.png',x:-76.25,y:-77.17,width:144,socket:{x:-25,y:33},anchors:[{x:-7,y:-43},{x:39,y:-13},{x:31,y:34},{x:-16,y:32},{x:-41,y:-11}]},
    side:{file:'bloom-side.png',x:-74.64,y:-74.41,width:144,socket:{x:40.8,y:61.2},anchors:[{x:7,y:-40},{x:40,y:-19},{x:17,y:21},{x:-30,y:27},{x:-33,y:-14}]}
  };
  const rotate=(p,angle)=>{const a=angle*Math.PI/180;return{x:p.x*Math.cos(a)-p.y*Math.sin(a),y:p.x*Math.sin(a)+p.y*Math.cos(a)};};
  const pose=seed=>poses[seed%3===1?'side':'cupped'];
  function socket(seed,rotation,worldWidth){const p=rotate(pose(seed).socket,rotation),scale=worldWidth/160;return{x:p.x*scale,y:p.y*scale};}
  const labels=(seed,rotation)=>pose(seed).anchors.map(p=>{const q=rotate(p,rotation);return{x:(80+q.x)/1.6,y:(80+q.y)/1.6};});
  const focus=(seed,index,rotation=0)=>rotate(pose(seed).anchors[index],rotation);
  const api={poses,pose,rotate,socket,labels,focus};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.GardenBotanicalPose=api;
})(typeof window==='undefined'?{}:window);
