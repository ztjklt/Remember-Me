/* One generated macro photograph, five separately addressable natural petals.
   Sectors partition the photograph; they do not draw the visible petal outline.
   Each local image counter-rotates so the assembled bloom retains its texture. */
(function(root){
  const previous=root.GardenArtwork;
  const photo='../../assets/brand/forget-me-not/v19/forget-me-not-macro.png';
  // Boundaries follow the valleys of this particular generated blossom.
  const edges=[-36,34,105,182,251,324];
  const n=v=>Number(v.toFixed(4));
  const point=a=>[n(Math.sin(a*Math.PI/180)*112),n(-Math.cos(a*Math.PI/180)*112)];
  function bloom(f,index){
    const petals=edges.slice(0,-1).map((edge,i)=>{
      const angle=(edge+edges[i+1])/2,a=point(edge-angle-.06),b=point(edges[i+1]-angle+.06),id=`v19-${index}-${i}`;
      const d=`M0 0 L${a.join(' ')} L${b.join(' ')}Z`;
      return `<g class="living-petal" transform="rotate(${angle})" data-petal-angle="${angle}"><defs><clipPath id="${id}-cut"><path class="living-petal-surface" d="${d}"/></clipPath><radialGradient id="${id}-fade" cx="0" cy="-43" r="45" gradientUnits="userSpaceOnUse" gradientTransform="translate(0 -43) scale(1 1.22) translate(0 43)"><stop offset="0" stop-color="white"/><stop offset=".58" stop-color="white"/><stop offset="1" stop-color="white"/></radialGradient><mask id="${id}-veil" maskUnits="userSpaceOnUse" x="-112" y="-112" width="224" height="224"><rect x="-112" y="-112" width="224" height="224" fill="url(#${id}-fade)"/></mask></defs><g clip-path="url(#${id}-cut)" mask="url(#${id}-veil)"><image class="petal-photo" href="${photo}" x="-73.3" y="-77.3" width="144" height="144" transform="rotate(${-angle})" preserveAspectRatio="xMidYMid meet"/></g></g>`;
    });
    return `<g class="living-bloom botanical-v19" transform="translate(${f.x} ${f.y}) rotate(${f.r}) scale(${f.s} ${n(f.s*f.tilt)})">${petals.join('')}</g>`;
  }
  root.GardenArtwork={...previous,bloom};
})(window);
