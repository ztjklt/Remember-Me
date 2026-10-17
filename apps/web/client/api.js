export class SessionClient {
  epoch=0; pending=new Set();
  reset(){this.epoch++;for(const c of this.pending)c.abort();this.pending.clear();}
  async request(path,{body,method='GET',audio=false}={}) {
    const epoch=this.epoch,controller=new AbortController();this.pending.add(controller);
    const timeout=setTimeout(()=>controller.abort(),120000);
    try {
      const response=await fetch(path,{method,body:body===undefined?undefined:JSON.stringify(body),headers:body===undefined?{}:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',signal:controller.signal});
      const result=audio && response.ok ? await response.blob() : await response.json().catch(()=>({}));
      if(epoch!==this.epoch)throw new DOMException('已切换空间','AbortError');
      if(!response.ok){const e=Error(result.error_message || result.detail?.message || (typeof result.detail==='string'?result.detail:'暂时无法完成，请稍后再试。'));e.status=response.status;throw e;}
      return result;
    } finally {clearTimeout(timeout);this.pending.delete(controller);}
  }
}
