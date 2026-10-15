"""Incremental JSON points for private synthesis preparation, never partial publication."""
import json
import re


def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate key')
        result[key]=value
    return result


class Points:
    def __init__(self):
        self.text='';self.pos=None;self.points=[];self.separator=False;self.ended=False
        self.decoder=json.JSONDecoder(object_pairs_hook=unique_object)

    def feed(self,text):
        self.text+=text
        if len(self.text)>65536:raise ValueError('output too large')
        if self.pos is None:
            match=re.match(r'^\s*\{\s*"points"\s*:\s*\[',self.text)
            if match is None:return []
            self.pos=match.end()
        output=[]
        while not self.ended:
            while self.pos<len(self.text) and self.text[self.pos].isspace():self.pos+=1
            if self.pos==len(self.text):break
            if self.text[self.pos]==']':self.ended=True;break
            if self.separator:
                if self.text[self.pos]!=',':raise ValueError('invalid separator')
                self.pos+=1;self.separator=False;continue
            try:value,end=self.decoder.raw_decode(self.text,self.pos)
            except json.JSONDecodeError:break
            if not isinstance(value,dict) or len(self.points)>=4:raise ValueError('invalid point')
            self.points.append(value);output.append(value);self.pos=end;self.separator=True
        return output

    def finish(self):
        value=json.loads(self.text,object_pairs_hook=unique_object)
        if not isinstance(value,dict) or value.get('points')!=self.points or not self.ended:
            raise ValueError('points mismatch')
        return value
