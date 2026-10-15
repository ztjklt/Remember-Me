"""Recorded technical review of this fictional sample, never a person's approval.

Explicit decisions below were checked against actual ASR evidence. The script
does not read the truth dossier or replace machine transcription.
"""
import json
import httpx
from ingest import BASE,VAR,STATE,request,save

FIELDS=['kind','title','text','evidence_ids','facets','time_text','place_text','aliases','same_event','recipient_label']
APPROVED_TITLES={'老车床螺丝松动','与周桂芳初次见面','女儿学美术的争执','修机器与过日子的看法',
    '拆收音机后找螺丝','电话短与挂念','老杜','给豆豆买画笔','对桂芳说多年辛劳',
    '叮嘱儿女工作与身体','想念孩子小时候','对录音被听的期望',
    '自述的家乡与工作','不替自己编没说过的话'}


def main():
    state=json.loads(STATE.read_text(encoding='utf8'))
    account=json.loads((VAR/'private/local-accounts.json').read_text(encoding='utf8'))['owner']
    audit={'basis':'fictional sample / technical text evidence review, NOT human listening or real-subject endorsement',
           'asr_modified':False,'profile_confirmations':0,'decisions':[]}
    with httpx.Client(base_url=BASE,headers={'Origin':BASE},trust_env=False,timeout=120) as c:
        request(c,'POST','/api/v1/accounts/login',json={k:account[k] for k in ['username','password']})
        root='/api/v1/workbench/subjects/'+state['subject_id']
        data=request(c,'GET',root+'/narrative');records=data['records'];sources=data['source_evidence']
        # Two explicit derived entries recover observed missing facet/quote,
        # with the exact actual source. No unsupported age or medical identity.
        extras=[('自述的家乡与工作','person','我是襄阳人，以前在机械厂上班修机器的。',['IDENTITY','EXPERIENCE']),
                ('不替自己编没说过的话','style','以后要是有人听这些录音，别把我说的太好，也别替我编那些没说过的话。',['EXPRESSION','WISHES'])]
        for title,kind,text,facets in extras:
            if any(r['title']==title for r in records):continue
            evidence=next(e for e in sources if text==e['excerpt'])
            r=request(c,'POST',root+'/narrative/records',json={'kind':kind,'title':title,'text':text,
                'facets':facets,'evidence_ids':[evidence['evidence_id']]})
            records.append(r);audit['decisions'].append({'id':r['id'],'action':'technical_add_exact_quote','source':evidence})
        for r in records:
            if r['title'] not in APPROVED_TITLES or r['status']!='pending':continue
            body={k:r[k] for k in FIELDS};before=body.copy()
            if r['title']=='与周桂芳初次见面':body['text']=r['text'].replace('1976年','76年')
            if r['title']=='修机器与过日子的看法':
                body['text']='讲述者说修机器不能拿锤子乱敲，要先弄明白哪里出了问题。他把这种做法延伸到过日子，也反思自己有时不爱听别人劝换办法，现在想想不一定都是对的。'
            if r['title']=='叮嘱儿女工作与身体':
                related=next(item for item in records if item['title']=='想念孩子小时候')
                body['text']+=' 同时，他说晚上饭桌上只有自己和妻子时，还是会想念孩子小时候的热闹。'
                body['evidence_ids']=list(dict.fromkeys(body['evidence_ids']+related['evidence_ids']))
                body['facets']=list(dict.fromkeys(body['facets']+['FEELINGS']))
            if body!=before:
                r=request(c,'PUT',root+'/narrative/records/'+r['id'],json={**body,'revision':r['revision']})
                audit['decisions'].append({'id':r['id'],'action':'technical_context_edit','before':before,'after':body})
            request(c,'POST',root+'/narrative/records/'+r['id']+'/confirm',json={'revision':r['revision']})
            audit['decisions'].append({'id':r['id'],'action':'technical_source_review','title':r['title'],
                                       'basis_evidence_ids':r['evidence_ids']})
        for r in request(c,'GET',root+'/profile-candidates')['items']:
            if r['status']=='pending' and '错怪' in r['statement']:
                request(c,'POST',root+'/profile-candidates/'+r['candidate_id']+'/reject')
                audit['decisions'].append({'id':r['candidate_id'],'action':'reject','reason':'指责不等于已证明错怪；模型审阅仍漏检'})
        save(VAR/'runtime/technical-review.json',audit)
        save(VAR/'runtime/narrative-reviewed.json',request(c,'GET',root+'/narrative'))
    print('Explicit technical story review saved; ASR unchanged; profiles not confirmed.')


if __name__=='__main__':main()
