import {catalog} from './catalog.js';
const base = new URL('./svg/', import.meta.url);
/** Decorative by default; the parent action provides its name. */
class MemoryGlyph extends HTMLElement {
  static observedAttributes = ['name','size','theme','treatment','label'];
  constructor(){super();this.attachShadow({mode:'open'});this.render=this.render.bind(this);}
  connectedCallback(){
    this.themeQuery=matchMedia('(prefers-color-scheme: dark)');
    this.contrastQuery=matchMedia('(prefers-contrast: more)');
    this.transparencyQuery=matchMedia('(prefers-reduced-transparency: reduce)');
    for(const query of [this.themeQuery,this.contrastQuery,this.transparencyQuery])query.addEventListener('change',this.render);
    this.observer=new MutationObserver(this.render);this.observer.observe(document.documentElement,{attributes:true,attributeFilter:['class','data-theme']});this.render();
  }
  disconnectedCallback(){this.observer?.disconnect();for(const q of [this.themeQuery,this.contrastQuery,this.transparencyQuery])q?.removeEventListener('change',this.render);}
  attributeChangedCallback(){if(this.isConnected)this.render();}
  render(){
    const name=Object.hasOwn(catalog,this.getAttribute('name')) ? this.getAttribute('name') : 'voice';
    const value=Number(this.getAttribute('size')||96),size=Number.isFinite(value)?Math.max(16,Math.min(192,value)):96;
    const theme=this.getAttribute('theme')||'auto';
    const pageTheme=document.documentElement.dataset.theme;
    const dark=theme==='dark'||theme==='auto'&&(pageTheme ? pageTheme==='dark' : document.documentElement.classList.contains('dark')||this.themeQuery?.matches);
    const requested=this.getAttribute('treatment')||'auto';
    const mode=this.contrastQuery?.matches||this.transparencyQuery?.matches?'flat':requested==='auto'?(size<=32?'flat':size<64?'duotone':'material'):['flat','duotone','material'].includes(requested)?requested:'flat';
    const img=document.createElement('img');img.src=new URL(`${name}-${dark?'dark':'light'}-${mode}.svg`,base);img.alt='';img.width=size;img.height=size;img.draggable=false;
    const style=document.createElement('style');style.textContent=':host{display:inline-flex;flex:none;vertical-align:middle;line-height:0;pointer-events:none}img{display:block;width:100%;height:100%;object-fit:contain}';
    this.style.width=`${size}px`;this.style.height=`${size}px`;
    const label=this.getAttribute('label');if(label){this.setAttribute('role','img');this.setAttribute('aria-label',label);this.removeAttribute('aria-hidden');}else{this.setAttribute('aria-hidden','true');this.removeAttribute('role');this.removeAttribute('aria-label');}
    this.shadowRoot.replaceChildren(style,img);
  }
}
if(!customElements.get('memory-glyph'))customElements.define('memory-glyph',MemoryGlyph);
