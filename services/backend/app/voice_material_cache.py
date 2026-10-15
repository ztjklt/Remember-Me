"""One ephemeral call, one version. No answer caching and no ORM objects."""
from copy import deepcopy
from threading import Lock


def clone(value):
    # AuthorizedSnapshot and its flat source mappings are immutable by design.
    # Copy the mutable candidate/trait lists, not MappingProxyType via pickle.
    copied=deepcopy({k:v for k,v in value.items() if k!='snapshot'})
    if 'snapshot' in value:copied['snapshot']=value['snapshot']
    return copied


class VoiceMaterialCache:
    def __init__(self):self.lock=Lock();self.key=None;self.value=None;self.closed=False
    def get(self,key):
        with self.lock:return clone(self.value) if self.value is not None and key==self.key else None
    def put(self,key,value):
        with self.lock:
            if not self.closed:self.key=key;self.value=clone(value)
    def clear(self):
        with self.lock:self.key=None;self.value=None;self.closed=True
