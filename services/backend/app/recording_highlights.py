"""Timestamp attention hints, never evidence of truth or guessed alignment."""
from .chinese_text import simplified_transcript

VERSION = 'recording-highlights-v1'
MAX_MS = 24 * 60 * 60 * 1000


def validated_sentences(rows):
    if not isinstance(rows, list) or len(rows) > 10_000:
        return []
    result = []
    last = -1
    for row in rows:
        if not isinstance(row, dict):
            return []
        start, end, text = row.get('begin_time'), row.get('end_time'), row.get('text')
        if (type(start) is not int or type(end) is not int or
                not 0 <= start < end <= MAX_MS or start < last or
                not isinstance(text, str) or not text.strip() or len(text) > 30_000):
            return []
        last = start
        result.append({'start_ms': start, 'end_ms': end, 'text': text.strip()})
    return result


def highlight_report(episode):
    metadata = episode.capture_metadata or {}
    transcript = episode.transcript or ''
    duration = episode.duration_ms or MAX_MS
    hardware = metadata.get('hardware', {})
    raw = hardware.get('markers', []) if isinstance(hardware, dict) else []
    markers = sorted({(m['offset_ms'], m.get('origin', 'phone')) for m in raw[:500]
        if isinstance(m, dict) and type(m.get('offset_ms')) is int
        and 0 <= m['offset_ms'] <= min(duration, MAX_MS)
        and isinstance(m.get('origin', 'phone'), str)
        and m.get('origin', 'phone') in {'phone', 'device'}}) if isinstance(raw, list) else []
    timeline = metadata.get('asr_timeline', [])
    timeline = validated_sentences([{'begin_time': row.get('start_ms'), 'end_time': row.get('end_ms'), 'text': row.get('text')}
        for row in timeline if isinstance(row, dict)]) if isinstance(timeline, list) else []
    mapped = set()
    spans = {}
    source_text = ''.join(simplified_transcript(row['text']).strip() for row in timeline)
    for point, origin in markers:
        for row in timeline:
            start, end = row['start_ms'], row['end_ms']
            if start >= point + 5000 or end <= max(0, point - 10000):
                continue
            quote = simplified_transcript(row['text']).strip()
            # After proofreading/review, only an exact unique quote is safe.
            # Repeated or rewritten sentences stay explicitly unaligned.
            offset = transcript.find(quote)
            source_offset = source_text.find(quote)
            if (not quote or offset < 0 or transcript.find(quote, offset + 1) >= 0
                    or source_text.find(quote, source_offset + 1) >= 0):
                continue
            mapped.add((point, origin))
            key = (offset, offset + len(quote))
            span = spans.setdefault(key, {'span_start': key[0], 'span_end': key[1],
                'excerpt': quote, 'start_ms': start, 'end_ms': end,
                'priority_weight': 2.0, 'markers': []})
            span['markers'].append({'offset_ms': point, 'origin': origin})
    return {'version': VERSION, 'state': ('no_markers' if not markers else
        'timestamps_unavailable' if not timeline else 'mapped' if len(mapped) == len(markers) else 'partially_mapped' if mapped else 'unmapped'),
        'marker_count': len(markers), 'mapped_count': len(mapped),
        'device_marker_count': sum(origin == 'device' for _, origin in markers),
        'phone_marker_count': sum(origin == 'phone' for _, origin in markers),
        'device_marker_pending': isinstance(hardware, dict) and hardware.get('device_marker_pending') is True,
        'markers': [{'offset_ms': point, 'origin': origin, 'mapped': (point, origin) in mapped}
                    for point, origin in markers],
        'unmapped_count': len(markers) - len(mapped), 'window_before_ms': 10000,
        'window_after_ms': 5000, 'spans': [spans[k] for k in sorted(spans)]}
