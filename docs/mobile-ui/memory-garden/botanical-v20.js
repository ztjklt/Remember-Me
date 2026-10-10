/* Macro photographs encode actual petal curvature and oblique views. The UI
   uses their measured anchors, never a CSS-skewed flat card. */
(function(root){
  const previous=root.GardenArtwork,P=root.GardenBotanicalPose,n=v=>Number(v.toFixed(4));
  const edges=[-36,34,105,182,251,324];
  const point=a=>[n(Math.sin(a*Math.PI/180)*112),n(-Math.cos(a*Math.PI/180)*112)];
  function bloom(f,index){
    const pose=P.pose(f.seed),photo=`../../assets/brand/forget-me-not/v20/${pose.file}`;
    const petals=edges.slice(0,-1).map((edge,i)=>{
      const angle=(edge+edges[i+1])/2,a=point(edge-angle-.06),b=point(edges[i+1]-angle+.06),id=`v20-${index}-${i}`,focus=P.rotate(pose.anchors[i],-angle);
      return `<g class="living-petal" transform="rotate(${angle})" data-petal-angle="${angle}" data-focal-x="${n(focus.x)}" data-focal-y="${n(focus.y)}"><defs><clipPath id="${id}-cut"><path class="living-petal-surface" d="M0 0 L${a.join(' ')} L${b.join(' ')}Z"/></clipPath><radialGradient id="${id}-fade" cx="${n(focus.x)}" cy="${n(focus.y)}" r="45" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="white"/><stop offset=".58" stop-color="white"/><stop offset="1" stop-color="white"/></radialGradient><mask id="${id}-veil" maskUnits="userSpaceOnUse" x="-112" y="-112" width="224" height="224"><rect x="-112" y="-112" width="224" height="224" fill="url(#${id}-fade)"/></mask></defs><g clip-path="url(#${id}-cut)" mask="url(#${id}-veil)"><image class="petal-photo" href="${photo}" x="${pose.x}" y="${pose.y}" width="${pose.width}" height="${pose.width}" transform="rotate(${-angle})" preserveAspectRatio="xMidYMid meet"/></g></g>`;
    });
    return `<g class="living-bloom botanical-v20" transform="translate(${f.x} ${f.y}) rotate(${f.r}) scale(${f.s} ${n(f.s*f.tilt)})">${petals.join('')}</g>`;
  }
  root.GardenArtwork={...previous,bloom};
})(window);
