/** Dependency-free, non-interactive brand component. Asset paths resolve beside this module. */
const asset = name => new URL(`./svg/${name}.svg`, import.meta.url).href;
export class RememberMeBrand extends HTMLElement {
  static observedAttributes = ['variant','size','theme','label','wordmark'];
  constructor() { super(); this.attachShadow({mode:'open'}); }
  connectedCallback() { this.render(); }
  attributeChangedCallback() { if(this.isConnected) this.render(); }
  render() {
    const size=Math.max(16,Math.min(512,Number(this.getAttribute('size'))||48));
    const requested=this.getAttribute('variant')||'auto';
    const variant=['material','flat','mono'].includes(requested)?requested:(size<64?'flat':'material');
    const dark=this.getAttribute('theme')==='dark';
    const label=this.getAttribute('label');
    const withText=this.hasAttribute('wordmark');
    this.shadowRoot.replaceChildren();
    const style=document.createElement('style');
    style.textContent=`:host{display:inline-flex;vertical-align:middle;color:var(--rm-brand-ink,${dark?'#EDF2FF':'#17243B'});max-width:100%}.lockup{display:inline-flex;align-items:center;gap:.65em;max-width:100%}.mark{display:block;width:${size}px;height:${size}px;flex:none;object-fit:contain}.mono{background:currentColor;mask:url('${asset('mark-mono')}') center/contain no-repeat;-webkit-mask:url('${asset('mark-mono')}') center/contain no-repeat}.name{font-family:system-ui,-apple-system,'Microsoft YaHei',sans-serif;font-size:var(--rm-brand-wordmark-size,1.25rem);font-weight:550;letter-spacing:.06em;line-height:1.5;overflow-wrap:anywhere}@media(forced-colors:active){.mono{background:CanvasText;forced-color-adjust:none}}`;
    const wrap=document.createElement('span');wrap.className='lockup';
    if(label){wrap.setAttribute('role','img');wrap.setAttribute('aria-label',label);}
    else if(!withText)wrap.setAttribute('aria-hidden','true');
    const mark=document.createElement(variant==='mono'?'span':'img');mark.className='mark'+(variant==='mono'?' mono':'');
    mark.setAttribute('aria-hidden','true');
    if(variant!=='mono'){mark.alt='';mark.src=asset('mark-'+variant+(variant==='flat'&&dark?'-dark':''));mark.width=size;mark.height=size;}
    wrap.append(mark);
    if(withText){const wordmark=document.createElement('span');wordmark.className='name';wordmark.textContent='勿忘我';wrap.append(wordmark);}
    this.shadowRoot.append(style,wrap);
    this.dataset.resolvedVariant=variant;
  }
}
if(!customElements.get('remember-me-brand'))customElements.define('remember-me-brand',RememberMeBrand);
