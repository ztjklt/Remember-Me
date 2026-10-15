"""Pure parsing and deterministic validation for opt-in voice experiments.

No service imports this module. Semantic review is deliberately NOT claimed by
the fast experiment; ordinary QuotedTwin remains unchanged.
"""
import json
import re
from time import monotonic, sleep
from app.quoted_twin import SYSTEM, quote_packet, SourceSelection, SourcePoint, render_ids, schema_errors
from app.errors import AIOutputInvalid, ProviderTimeout, ProviderUnavailable, ProviderRateLimited
from app.cancellation import check_cancelled
from app.twin import TwinOutput

class StreamFailure(ValueError):
    pass

class SSE:
    def __init__(self):
        self.pending=b'';self.data=[];self.total=0;self.done=False;self.stopped=False
    def feed(self, chunk):
        self.total+=len(chunk)
        if self.total>1_048_576:raise StreamFailure('stream too large')
        self.pending+=chunk
        while b'\n' in self.pending:
            line,self.pending=self.pending.split(b'\n',1);line=line.rstrip(b'\r')
            if line.startswith(b'data:'):
                self.data.append(line[5:].lstrip())
            elif not line and self.data:
                raw=b'\n'.join(self.data);self.data=[]
                if self.done:raise StreamFailure('data after DONE')
                if raw==b'[DONE]':self.done=True;continue
                try:item=json.loads(raw)
                except (ValueError,UnicodeError) as exc:raise StreamFailure('invalid SSE JSON') from exc
                if not isinstance(item,dict) or item.get('error'):raise StreamFailure('provider error')
                for choice in item.get('choices',[]):
                    reason=choice.get('finish_reason')
                    if reason is not None:
                        if reason!='stop':raise StreamFailure('incomplete completion')
                        self.stopped=True
                yield item
    def finish(self):
        if not self.done or not self.stopped or self.pending.strip() or self.data:
            raise StreamFailure('truncated SSE')


def unique_object(pairs):
    obj={}
    for key,value in pairs:
        if key in obj:raise StreamFailure('duplicate JSON key')
        obj[key]=value
    return obj

class CompletePoints:
    def __init__(self, audit=None):
        self.text='';self.pos=None;self.points=[];self.separator=False;self.ended=False
        self.audit=audit
        self.decoder=json.JSONDecoder(object_pairs_hook=unique_object)
    def feed(self, text):
        self.text+=text
        if self.audit is not None:self.audit['partial_selection_text']=self.text[:65536]
        if len(self.text)>65536:raise StreamFailure('selection too large')
        if self.pos is None:
            prefix=re.match(r'^\s*\{\s*"points"\s*:\s*\[',self.text)
            if prefix is None:return []
            self.pos=prefix.end()
        emitted=[]
        while not self.ended:
            while self.pos<len(self.text) and self.text[self.pos].isspace():self.pos+=1
            if self.pos==len(self.text):break
            if self.text[self.pos]==']':self.ended=True;break
            if self.separator:
                if self.text[self.pos]!=',':raise StreamFailure('invalid point separator')
                self.pos+=1;self.separator=False;continue
            try:value,end=self.decoder.raw_decode(self.text,self.pos)
            except json.JSONDecodeError:break
            try:SourcePoint.model_validate(value)
            except ValueError as exc:raise StreamFailure('invalid point') from exc
            if len(self.points)>=4:raise StreamFailure('too many points')
            self.points.append(value);emitted.append(value);self.pos=end;self.separator=True
        return emitted
    def finish(self):
        try:
            value=json.loads(self.text,object_pairs_hook=unique_object)
            SourceSelection.model_validate(value)
        except ValueError as exc:raise StreamFailure('incomplete or invalid selection') from exc
        if value['points']!=self.points:raise StreamFailure('released points mismatch')
        return value

def fast_answer(chat, payload):
    """Same v16 selection/repair budget; stop before the semantic review stage."""
    if not payload.candidates:
        return TwinOutput(answer='现有记录还不足以确定。',response_type='UNKNOWN',
            evidence_ids=[],confidence=0,model_version='no-evidence')
    start=monotonic();calls=0
    packet,_=quote_packet(payload)
    request={**packet,'response_schema':SourceSelection.model_json_schema()}
    def complete(prompt,body):
        nonlocal calls
        for attempt in range(2):
            check_cancelled()
            if calls>=2 or monotonic()-start>65:raise ProviderTimeout('Quote request budget exhausted')
            calls+=1
            try:return chat.complete(prompt,body)
            except ProviderRateLimited:raise
            except (ProviderTimeout,ProviderUnavailable):
                if attempt or calls>=2 or monotonic()-start>65:raise
                sleep(.3)
        raise AssertionError('unreachable')
    raw,model=complete(SYSTEM,request)
    check_cancelled()
    try:output,_=render_ids(raw,payload,model)
    except AIOutputInvalid as exc:
        raw,model=complete(SYSTEM+'\n这是唯一一次修正。草稿不是事实。严格依据原始sources修正所选编号或JSON格式。总长过长时选择能回答的更少、更短的来源；不得通过伪造未知躲过校验。',
            {**request,'rejected_draft':raw,'validation_error':exc.message,
             'schema_errors':schema_errors(raw,SourceSelection)})
        check_cancelled()
        output,_=render_ids(raw,payload,model)
    return output
