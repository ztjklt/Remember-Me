"""Numerical reference-sample QA. This does not verify speech or identity."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from collections.abc import Sequence


@dataclass(frozen=True)
class SampleQuality:
    duration_seconds: float
    rms: float
    audible_seconds: float
    clipping_ratio: float


def assess_pcm16(samples: Sequence[int], sample_rate: int) -> SampleQuality:
    if sample_rate <= 0 or not samples:
        raise ValueError("声音样本为空或采样率无效，请重新录制。")
    duration = len(samples) / sample_rate
    if not 5 <= duration <= 15:
        raise ValueError("请录制 5 到 15 秒的自然说话声音。")
    energy = sqrt(sum(int(value) ** 2 for value in samples) / len(samples))
    if energy < 180:
        raise ValueError("样本声音太轻或几乎无声，请重新录制。")
    clipping = sum(abs(int(value)) >= 32700 for value in samples) / len(samples)
    if clipping > 0.02:
        raise ValueError("样本声音失真较多，请远离麦克风重新录制。")
    frame_size = max(1, int(sample_rate * 0.02))
    audible_samples = 0
    for start in range(0, len(samples), frame_size):
        frame = samples[start:start + frame_size]
        if sqrt(sum(int(value) ** 2 for value in frame) / len(frame)) >= 180:
            audible_samples += len(frame)
    audible = audible_samples / sample_rate
    if audible < 2:
        raise ValueError("样本中的有效声音太短，请多说几句话后重新录制。")
    return SampleQuality(duration, energy, audible, clipping)
