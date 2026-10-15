import pytest


def test_normal_audio_delayed_then_delivered_in_bursts_is_not_a_flood():
    from app.pcm_rate import PcmRateLimiter
    limiter=PcmRateLimiter(now=0)
    # Exactly realtime overall; 3-second network bursts can cross window edges.
    for now in (3,6,9,12,15,18,21,24,27,30):
        limiter.consume(32000*3,now=now)


def test_fixed_window_false_positive_reproduced_but_bucket_accepts():
    from app.pcm_rate import PcmRateLimiter
    limiter=PcmRateLimiter(now=0)
    # Seven seconds of speech arriving after 7s, followed by normal live frames.
    # Old reset-at-first-receive window counts >7s in the following 5s.
    limiter.consume(32000*7,now=7)
    for step in range(1,51):limiter.consume(3200,now=7+step/10)


def test_unbounded_or_sustained_fast_audio_is_still_rejected():
    from app.pcm_rate import PcmRateLimiter
    from app.realtime_providers import RealtimeFailure
    limiter=PcmRateLimiter(now=0)
    with pytest.raises(RealtimeFailure):limiter.consume(32000*8,now=0)
    limiter=PcmRateLimiter(now=0)
    with pytest.raises(RealtimeFailure):
        for step in range(100):limiter.consume(6400,now=step/10)


def test_idle_time_does_not_accumulate_unlimited_credit():
    from app.pcm_rate import PcmRateLimiter
    from app.realtime_providers import RealtimeFailure
    limiter=PcmRateLimiter(now=0)
    with pytest.raises(RealtimeFailure):limiter.consume(32000*8,now=10000)
