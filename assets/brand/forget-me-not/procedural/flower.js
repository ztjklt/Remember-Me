/* Original, deterministic 2.5D corolla study. No external meshes, textures or runtime.
 * See README.md for formulas, reference projects and the photographic reference.
 * The shader is a height field, not a botanical simulation or a rotatable 3D mesh. */
const fallback = new URL('../v2/svg/mark-light.svg', import.meta.url).href;
const vertex = `attribute vec2 position; void main(){gl_Position=vec4(position,0.,1.);}`;
const fragment = `
precision highp float;
uniform vec2 resolution;
uniform float cup, detail, lightAngle;
const float PI=3.14159265359;
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x),f.y);}
float radius(float a){
  float delta=atan(sin(5.*(a-PI*.5)),cos(5.*(a-PI*.5)))/5.;
  // Radial intersection with five overlapping circles gives broad, rounded petals.
  float d=.49,b=.405;
  float roundPetal=d*cos(delta)+sqrt(max(.001,b*b-d*d*sin(delta)*sin(delta)));
  return roundPetal-.018*exp(-pow(delta/.075,2.))+.012*sin(3.*a+.5)+.006*cos(7.*a);
}
float heightAt(vec2 p){
  float r=length(p),a=atan(p.y,p.x),q=r/radius(a);
  float bowl=(.13*q*q+.12*pow(q,8.)-.12*exp(-24.*r*r))*cup;
  float folds=.020*cos(5.*(a-PI*.5))*smoothstep(.15,.55,r);
  return bowl+folds+.014*sin(3.*a+.8)*r*r;
}
void main(){
  vec2 p=(gl_FragCoord.xy-resolution*vec2(.46,.635))/(resolution.x*.29);
  p.y/= .94;
  float r=length(p),a=atan(p.y,p.x),edge=radius(a),q=r/edge;
  float aa=3.0/resolution.x;
  float alpha=1.-smoothstep(1.-aa,1.+aa,q);
  if(alpha<.001) discard;
  float e=.003;
  vec3 n=normalize(vec3(-(heightAt(p+vec2(e,0))-heightAt(p-vec2(e,0)))/(2.*e),-(heightAt(p+vec2(0,e))-heightAt(p-vec2(0,e)))/(2.*e),1.));
  vec3 light=normalize(vec3(cos(lightAngle)*.95,sin(lightAngle)*.95,.85));
  float lambert=max(dot(n,light),0.);
  float lobeAngle=atan(sin(5.*(a-PI*.5)),cos(5.*(a-PI*.5)))/5.;
  // Fine radial fans vary in width; detail only modulates material, never the silhouette.
  float fan=lobeAngle*(26.+10.*r)+.28*sin(r*9.+a*3.);
  float vein=pow(.5+.5*cos(fan*6.28318),18.);
  float fine=pow(.5+.5*cos(fan*14.2+r*6.),24.);
  float grain=noise(p*245.)-.5;
  float cloud=noise(p*9.)-.5;
  vec3 color=mix(vec3(.43,.60,.65),vec3(.72,.81,.81),smoothstep(.19,.96,r));
  color+=cloud*.022;
  color-=(vein*.060+fine*.023)*detail*smoothstep(.20,.40,r)*(1.-smoothstep(.88,1.,q));
  color+=grain*.035*detail;
  color*=.63+.48*lambert;
  // Broad, matte light: no plastic-looking hard specular highlight.
  color+=vec3(.045,.052,.042)*pow(max(dot(n,normalize(light+vec3(0,0,1))),0.),12.);
  color+=vec3(.065,.061,.047)*smoothstep(.91,1.,q);
  float throat=.18+.010*cos(5.*(a-PI*.5));
  float cream=1.-smoothstep(throat-.018,throat+.02,r);
  vec3 creamColor=vec3(.94,.91,.74)*(.78+.23*lambert);
  color=mix(color,creamColor,cream);
  float gold=1.-smoothstep(.113,.137,r);
  vec3 goldColor=vec3(.77,.59,.25)+.07*cos(5.*a)*vec3(1.,.8,.3);
  goldColor*=.87+.17*lambert;
  goldColor+=grain*.08;
  color=mix(color,goldColor,gold);
  float eye=1.-smoothstep(.043,.057,r);
  color=mix(color,vec3(.21,.28,.20),eye);
  gl_FragColor=vec4(color,alpha);
}`;

class BotanicalFlower extends HTMLElement {
  static observedAttributes = ['cup', 'detail', 'light'];
  constructor() {
    super();
    this.attachShadow({mode:'open'}).innerHTML = `
      <style>:host{display:block;aspect-ratio:400/440;position:relative}svg,canvas,img{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}canvas{filter:drop-shadow(0 3px 2px #25423518)}img{object-fit:contain} [hidden]{display:none!important}</style>
      <img src="${fallback}" alt="" hidden>
      <svg viewBox="0 0 400 440" aria-hidden="true">
        <defs>
          <linearGradient id="stem"><stop stop-color="#365843"/><stop offset=".45" stop-color="#809571"/><stop offset="1" stop-color="#42684D"/></linearGradient>
          <linearGradient id="leaf" x1="0" y1="1" x2="1" y2="0"><stop stop-color="#436347"/><stop offset=".5" stop-color="#85976E"/><stop offset=".52" stop-color="#607F59"/><stop offset="1" stop-color="#ADB28A"/></linearGradient>
          <radialGradient id="bud" cx=".3" cy=".2" r=".8"><stop stop-color="#C5C4CE"/><stop offset=".5" stop-color="#9FAAB9"/><stop offset="1" stop-color="#677D82"/></radialGradient>
        </defs>
        <path d="M185 162 C177 201 178 242 202 286 C232 344 284 358 263 382 C245 402 193 400 160 388" fill="none" stroke="url(#stem)" stroke-width="4.2" stroke-linecap="round"/>
        <path d="M189 255 C233 237 298 193 307 143 C311 125 307 115 303 110" fill="none" stroke="url(#stem)" stroke-width="2.7" stroke-linecap="round"/>
        <path d="M202 286 C235 278 260 253 266 229 C239 227 210 244 202 286Z" fill="url(#leaf)"/>
        <path d="M203 285 Q231 262 263 232 M220 271 L223 250 M228 265 L248 258 M236 256 L239 241" fill="none" stroke="#C4CDAA" stroke-width=".7" opacity=".65"/>
        <path d="M186 246 C159 235 145 218 143 198 C165 201 181 219 186 246Z" fill="url(#leaf)"/>
        <path d="M184 242 Q162 218 146 202" fill="none" stroke="#CAD2B4" stroke-width=".7" opacity=".7"/>
        <g transform="translate(26 -17)"><ellipse cx="277" cy="127" rx="12" ry="16" transform="rotate(-20 277 127)" fill="url(#bud)"/>
        <path d="M280 143 Q263 140 263 122 Q271 135 280 140 Q286 130 285 116 Q293 135 280 143" fill="#617F58"/>
        <path d="M272 113 Q269 124 280 137 M278 112 Q277 121 283 130" fill="none" stroke="#E0DCDA" stroke-width=".8" opacity=".55"/></g>
      </svg><canvas aria-hidden="true"></canvas>`;
  }
  connectedCallback() {
    if (!this.hasAttribute('role')) this.setAttribute('role','img');
    if (!this.hasAttribute('aria-label')) this.setAttribute('aria-label','五瓣勿忘我：微弯的雾蓝花瓣、金色花心、一枝花苞与叶片');
    this.canvas=this.shadowRoot.querySelector('canvas');
    this.onLost=e=>{e.preventDefault();this.useFallback();};
    this.onRestored=()=>this.init();
    this.canvas.addEventListener('webglcontextlost',this.onLost);
    this.canvas.addEventListener('webglcontextrestored',this.onRestored);
    this.observer=new ResizeObserver(()=>this.schedule());
    this.observer.observe(this);
    this.init();
  }
  init(){
    try {
      const gl=this.canvas.getContext('webgl',{alpha:true,antialias:false,premultipliedAlpha:false,powerPreference:'low-power'});
      if(!gl) throw new Error('WebGL unavailable');
      this.gl=gl;
      const shader=(type,source)=>{const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s));return s;};
      const vs=shader(gl.VERTEX_SHADER,vertex),fs=shader(gl.FRAGMENT_SHADER,fragment);
      this.program=gl.createProgram();gl.attachShader(this.program,vs);gl.attachShader(this.program,fs);gl.linkProgram(this.program);
      gl.deleteShader(vs);gl.deleteShader(fs);
      if(!gl.getProgramParameter(this.program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(this.program));
      gl.useProgram(this.program);
      this.buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,this.buffer);
      gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);
      const p=gl.getAttribLocation(this.program,'position');gl.enableVertexAttribArray(p);gl.vertexAttribPointer(p,2,gl.FLOAT,false,0,0);
      this.uniforms=Object.fromEntries(['resolution','cup','detail','lightAngle'].map(k=>[k,gl.getUniformLocation(this.program,k)]));
      this.shadowRoot.querySelector('img').hidden=true;this.canvas.hidden=false;this.shadowRoot.querySelector('svg').hidden=false;
      this.dataset.renderer='webgl';this.schedule();
    }catch(error){this.useFallback();console.warn('Botanical study uses the SVG fallback:',error.message);}
  }
  useFallback(){this.dataset.renderer='svg';this.shadowRoot.querySelector('img').hidden=false;this.canvas.hidden=true;this.shadowRoot.querySelector('svg').hidden=true;}
  attributeChangedCallback(){this.schedule();}
  schedule(){
    if(!this.isConnected||!this.gl||this.frame)return;
    this.frame=requestAnimationFrame(()=>{this.frame=0;this.draw();});
  }
  draw(){
    if(this.dataset.renderer!=='webgl')return;
    const width=this.getBoundingClientRect().width;
    if(!width)return;
    const gl=this.gl,dpr=Math.min(devicePixelRatio||1,2);
    const w=Math.min(960,Math.round(width*dpr)),h=Math.round(w*1.1);
    if(this.canvas.width!==w||this.canvas.height!==h){this.canvas.width=w;this.canvas.height=h;}
    gl.viewport(0,0,w,h);gl.useProgram(this.program);
    gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
    const value=(name,def,min,max)=>{const raw=this.getAttribute(name);const n=raw===null?def:Number(raw);return Math.min(max,Math.max(min,Number.isFinite(n)?n:def));};
    gl.uniform2f(this.uniforms.resolution,w,h);
    gl.uniform1f(this.uniforms.cup,value('cup',.65,0,1.4));
    gl.uniform1f(this.uniforms.detail,value('detail',.55,0,1));
    gl.uniform1f(this.uniforms.lightAngle,value('light',125,0,360)*Math.PI/180);
    gl.drawArrays(gl.TRIANGLES,0,6);
  }
  disconnectedCallback(){
    this.observer?.disconnect();cancelAnimationFrame(this.frame);this.frame=0;
    this.canvas?.removeEventListener('webglcontextlost',this.onLost);this.canvas?.removeEventListener('webglcontextrestored',this.onRestored);
    if(this.gl){this.gl.deleteBuffer(this.buffer);this.gl.deleteProgram(this.program);this.gl=null;}
  }
}
customElements.define('botanical-flower',BotanicalFlower);
