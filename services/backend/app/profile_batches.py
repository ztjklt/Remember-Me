"""Plan bounded proposals without cutting a sentence or separating one recording.

Each batch produces observations, not a global replacement personality. The
worker validates every batch before it publishes any candidate.
"""


def plan_profile_batches(materials, *, max_chars=24000, max_batches=12):
    if max_chars < 1 or max_batches < 1:
        raise ValueError('人物归纳批次上限无效')
    episodes, known = {}, {}
    for source in materials:
        identity = source['evidence_id']
        if identity in known:
            if known[identity] != source:
                raise ValueError('重复证据编号的内容不一致')
            continue
        known[identity] = source
        episodes.setdefault(source['episode_id'], []).append(source)
    batches, current, size = [], [], 0
    for group in episodes.values():
        count = sum(len(m['excerpt']) for m in group)
        if count > max_chars:
            raise ValueError('单段完整录音的有效证据超过人物归纳上限；请先分段核对，未截断原文。')
        if current and size + count > max_chars:
            batches.append(current)
            current, size = [], 0
        current.extend(group)
        size += count
    if current:
        batches.append(current)
    if len(batches) > max_batches:
        raise ValueError('人物归纳超过本轮批次上限；请缩小范围后重试，尚未调用模型。')
    return batches
