"""Normalize Chinese script only; never infer names or repair ASR facts."""
from functools import lru_cache
from opencc import OpenCC

NORMALIZATION_VERSION = 'opencc-t2s-0.1.7'

@lru_cache(maxsize=1)
def _converter():
    return OpenCC('t2s')

def simplified_transcript(text: str) -> str:
    return _converter().convert(text)
