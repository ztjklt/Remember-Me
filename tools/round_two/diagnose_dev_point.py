"""One real request sequence for an explicitly captured fictional case, no retries."""
import argparse,json,sys
from pathlib import Path
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'services/backend/var/paired-delivery'


def main():
    p=argparse.ArgumentParser();p.add_argument('case');p.add_argument('--version',default='v3');args=p.parse_args()
    if args.case.rsplit('-q',1)[0] not in {'bus_driver','firefighter','life_review'}:raise SystemExit('Only named synthetic cases')
    path=OUT/(args.case+'-'+args.version+'-diagnostic.json')
    if path.exists():raise SystemExit('Existing diagnostic preserved; no silent retry')
    sys.path.insert(0,str(ROOT/'services/ai-core'))
    from app.twin import TwinInput
    from app.grounded_twin import GroundedTwin,VERSION
    from app.providers.weixin import WeixinChat
    env={**dotenv_values(ROOT/'services/backend/.env'),**dotenv_values(ROOT/'services/ai-core/.env')}
    chat=WeixinChat(api_key=env['WEIXIN_CHAT_API_KEY']);calls=[]
    class Capture:
        def complete(self,system,payload):
            raw,model=chat.complete(system,payload);calls.append({'raw':raw,'model':model});return raw,model
    result={'case':args.case,'prompt_version':VERSION,'fictional_material':True,'calls':calls}
    try:result['answer']=GroundedTwin(Capture()).answer(TwinInput.model_validate_json((OUT/(args.case+'-packet.json')).read_text(encoding='utf8'))).model_dump()
    except Exception as exc:result['error']=str(exc)
    finally:chat.close();path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(args.case,result.get('error','returned'))


if __name__=='__main__':main()
