"""Export timing/failure metadata only; raw text/audio/packets remain private."""
import argparse
import json
import statistics
from pathlib import Path


FIELDS = ('case','mode','status','review','first_pcm_ms','validated_text_ms','total_ms',
          'first_token_ms','first_point_ms','stream_done_ms','pcm_bytes',
          'error','error_code','http_status','stream_stage','packet_sha256',
          'scope','requested_model','prompt_version')


def main(args):
    rows=[]
    for folder in ('round1','round2','final'):
        for file in sorted((Path(args.root)/folder).glob('*.json')):
            raw=json.loads(file.read_text(encoding='utf-8'))
            row={k:raw[k] for k in FIELDS if k in raw}
            row['batch']=folder
            row['request_count']=len(raw.get('calls',[])) or len(raw.get('stream_attempts',[])) or 1
            if row['mode']=='C' and 'first_point_ms' in row:
                row['point_to_json_end_ms']=round(row['stream_done_ms']-row['first_point_ms'],3)
            rows.append(row)
    stats=[]
    for batch in ('round1','round2','final'):
        for mode in 'ABC':
            group=[r for r in rows if r['batch']==batch and r['mode']==mode]
            success=[r for r in group if r['status']=='ok']
            samples=[r['first_pcm_ms'] for r in success]
            stats.append(dict(batch=batch,mode=mode,total=len(group),protocol_success=len(success),
                median_first_pcm_ms=round(statistics.median(samples),3) if samples else None,
                min_first_pcm_ms=min(samples) if samples else None,
                max_first_pcm_ms=max(samples) if samples else None))
    result={'measurement':'LLM selection through first-sentence PCM on ECS; no ASR or phone playback',
            'quality':'Protocol success does not assess semantic correctness; see manual review in report.',
            'rows':rows,'summary':stats}
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(stats,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--output',required=True)
    main(p.parse_args())
