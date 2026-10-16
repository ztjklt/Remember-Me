"""Bounded attention priority; never change evidence or confidence."""

INSTRUCTION = ('录音重点只表示用户希望关注的内容，不表示更真实、更确定或更能代表人格。'
    '优先覆盖 priority_weight=2 的来源，并保留相关上下文、否定、条件、反例和转述。'
    '普通来源仍需阅读；不得因重点而提高 confidence、编造记忆或忽略相反证据。')


def validated_highlights(payload):
    context = getattr(payload, 'subject_context', None) or {}
    report = context.get('recording_highlights', {})
    if not isinstance(report, dict) or report.get('version') != 'recording-highlights-v1':
        return []
    spans = report.get('spans', [])
    if not isinstance(spans, list):
        return []
    result = []
    for row in spans[:500]:
        if not isinstance(row, dict):
            continue
        start, end = row.get('span_start'), row.get('span_end')
        if (type(start) is not int or type(end) is not int or
                not 0 <= start < end <= len(payload.transcript) or
                payload.transcript[start:end] != row.get('excerpt')):
            continue
        result.append({'span_start': start, 'span_end': end, 'excerpt': payload.transcript[start:end],
                       'priority_weight': 2.0})
    return result


def overlaps(start, end, spans):
    return any(start < s['span_end'] and end > s['span_start'] for s in spans)


def annotate_output(payload, output):
    spans = validated_highlights(payload)
    evidence = {e.evidence_id: e for e in output.evidence}
    for memory in output.memory_items:
        # Recompute; never accept provider-made priority metadata.
        metadata = dict(memory.metadata or {})
        metadata.pop('recording_priority', None)
        supporting = [evidence[eid] for eid in memory.evidence_ids if eid in evidence]
        matched = [s for s in spans if any(e.span_start is not None and e.span_end is not None
            and overlaps(e.span_start, e.span_end, [s]) for e in supporting)]
        if matched:
            metadata['recording_priority'] = {'version': 'recording-highlights-v1',
                'weight': 2.0, 'basis': 'user_marker',
                'spans': [{'span_start': s['span_start'], 'span_end': s['span_end']} for s in matched]}
        memory.metadata = metadata or None
    output.memory_items.sort(key=lambda m: 0 if (m.metadata or {}).get('recording_priority') else 1)
    return output
