"""Recovery rules for the authorized fictional evaluation, not product facts."""
import json,re,time
import httpx
from speech_pipeline import save,sha

def choose_audio(folder,name,meta):
    filename=meta.get('audio_file',name+'.wav')
    path=folder/filename
    if path.resolve().parent!=folder.resolve():raise ValueError('audio reference outside episode folder')
    return path

def publish_repair(audio,record,data,meta):
    # Immutable generation: concurrent readers either see the old manifest/audio
    # or the new one. A crash before the JSON switch cannot remove the old pair.
    digest=sha(data);versioned=audio.with_name(audio.stem+'-repaired-'+digest[:16]+'.wav')
    if versioned.exists():
        if sha(versioned.read_bytes())!=digest:raise ValueError('immutable audio hash mismatch')
    else:
        temporary=versioned.with_suffix('.wav.tmp');temporary.write_bytes(data);temporary.replace(versioned)
    backup=record.with_name(record.stem+'-before-repair.json')
    if not backup.exists():backup.write_bytes(record.read_bytes())
    save(record,meta|{'audio_file':versioned.name,'audio_sha256':digest})

def record_failure(row,exc,now):
    message=str(exc)
    transient=isinstance(exc,(httpx.TimeoutException,httpx.NetworkError)) or bool(re.search(r'HTTP (429|502|503|504)\b',message))
    row.setdefault('failure_history',[]).append({'at':now,'error':message,'transient':transient})
    if transient:
        attempts=row.get('transport_attempts',0)+1;row['transport_attempts']=attempts
        if attempts<3:
            row['retry_after']=now+30*(2**(attempts-1));return
    row['blocked']=message

def qa_state(state,pid):
    item=state.setdefault('qa',{}).setdefault(pid,{})
    item.setdefault('checks',[])
    return item

def check_correction(person,old,story):
    # Test oracle only. These values are never sent to a model or patched into ASR.
    years={'bus_driver':('1986','1987'),'firefighter':('2017','2018'),'life_review':('2008','2009')}
    before,after=years[person]
    def norm(s):return re.sub(r'[^\w]','',s.translate(str.maketrans('〇零一二三四五六七八九','00123456789')))
    if before not in norm(old['content']):raise ValueError('correction target does not contain expected prior claim')
    matches=[]
    for memory in story['memories']:
        if after not in norm(memory['content']):continue
        for e in memory['evidence']:
            quote=norm(e['excerpt'])
            if before in quote and after in quote and any(v in quote for v in ('纠正','改口','不是','不对','说错','更正')):
                matches.append(e['evidence_id'])
    if not matches:raise ValueError('correction meaning is missing from actual ASR/evidence; prior fact remains active')
    return {'status':'passed_test_oracle','before':before,'after':after,'matching_evidence_ids':list(dict.fromkeys(matches))}


def technical_phase(state,expected=60):
    checks=[c for p in state.get('qa',{}).values() for c in p.get('checks',[])]
    good=sum('result' in c and not c.get('error') for c in checks)
    profiles=state.get('profiles',{})
    if good==expected and profiles and all(p.get('status')=='complete' for p in profiles.values()):
        return 'technical_requests_finished_quality_review_pending'
    return 'technical_partial_failures'
