"""Transport-only context for already authorized, current Twin evidence.

Do not add raw neighboring text here: effective_materials may have masked it.
Keep narrative fingerprints unchanged when evolving the internal Twin protocol.
"""
from .models import Episode, Evidence, as_utc


def contextual_evidence(session, sources):
    result = {}
    for id, source in sources.items():
        episode = session.get(Episode, source['episode_id'])
        evidence = session.get(Evidence, id)
        item = {k: source[k] for k in ('evidence_id','excerpt','source_type','episode_id','temporal_context')}
        item['recorded_at'] = as_utc(episode.recorded_at).isoformat()
        # A written correction belongs to this recording but is not an audio
        # quotation; never give it the replaced source's character position.
        if evidence and source['source_type'] != 'CALIBRATION' and evidence.span_start is not None and evidence.span_end is not None:
            if (episode.transcript or '')[evidence.span_start:evidence.span_end] == source['excerpt']:
                item.update(span_start=evidence.span_start, span_end=evidence.span_end)
        result[id] = item
    return result
