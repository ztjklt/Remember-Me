"""Bound PCM intake without treating a network catch-up burst as faster speech."""
import logging
import time
from .realtime_providers import RealtimeFailure


class PcmRateLimiter:
    rate=32000  # mono PCM16 at 16 kHz
    capacity=7*rate  # same maximum burst bytes as the previous window

    def __init__(self, *, now=None):
        self.updated=time.monotonic() if now is None else now
        self.tokens=float(self.capacity)

    def consume(self, size, *, now=None):
        now=time.monotonic() if now is None else now
        elapsed=max(0,now-self.updated)
        self.tokens=min(self.capacity,self.tokens+elapsed*self.rate)
        self.updated=max(self.updated,now)
        # A byte of tolerance avoids floating-point clock rounding at exact rate.
        if size>self.tokens+1:
            logging.getLogger(__name__).warning('PCM intake exceeded: frame_bytes=%d available_bytes=%d gap_ms=%d',size,int(self.tokens),int(elapsed*1000))
            raise RealtimeFailure('AUDIO_RATE_LIMIT')
        self.tokens=max(0,self.tokens-size)
