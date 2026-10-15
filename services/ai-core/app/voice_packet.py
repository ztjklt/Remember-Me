"""Lossless structural compaction; no summarization, slicing, or evidence filtering."""
from copy import deepcopy

COMPACT_INSTRUCTION='''资料用紧凑表格表示：每组recordings的sources是一组行，列名见该组source_columns；source_defaults为每行共用字段。confirmed_understanding同样按understanding_columns读。所有原文、条件、时间、反例完整保留；按列名还原理解，来源编号仍是id。'''


def compact_packet(packet):
    result=deepcopy(packet)
    for recording in result.get('recordings',[]):
        sources=recording.get('sources',[])
        defaults={}
        if sources:
            for key in ('type','temporal_context'):
                if key in sources[0] and all(key in s and s[key]==sources[0][key] for s in sources):defaults[key]=sources[0][key]
        columns=list(dict.fromkeys(k for s in sources for k in s if k not in defaults))
        # Omission and explicit null differ, so record field presence for rare mixed rows.
        present=[list(s.keys()) for s in sources]
        mixed=bool(sources) and any(set(s)!=set(sources[0]) for s in sources)
        recording['source_columns']=columns;recording['source_defaults']=defaults
        recording['sources']=[[s.get(k) for k in columns] for s in sources]
        if mixed:recording['source_fields']=present
    values=result.get('confirmed_understanding',[])
    if values and all(set(v)=={'text','source_ids'} for v in values):
        result['understanding_columns']=['text','source_ids']
        result['confirmed_understanding']=[[v['text'],v['source_ids']] for v in values]
    return result


def expand_packet(packet):
    result=deepcopy(packet)
    for recording in result.get('recordings',[]):
        columns=recording.pop('source_columns');defaults=recording.pop('source_defaults')
        fields=recording.pop('source_fields',None)
        rows=[]
        for i,row in enumerate(recording['sources']):
            source={**defaults,**dict(zip(columns,row,strict=True))}
            if fields is not None:source={k:source[k] for k in fields[i]}
            rows.append(source)
        recording['sources']=rows
    if result.pop('understanding_columns',None):
        result['confirmed_understanding']=[dict(text=t,source_ids=ids) for t,ids in result['confirmed_understanding']]
    return result
