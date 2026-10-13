"""Export additive mobile response schema from the shared draft schema."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
DIR=ROOT/'packages/contracts/schemas'
draft=json.loads((DIR/'narrative-draft-v1.schema.json').read_text(encoding='utf8'))
string={'type':'string'}
source={'type':'object','additionalProperties':False,'required':['evidence_id','episode_id','excerpt','source_type','temporal_context'],'properties':{
 'evidence_id':string,'episode_id':string,'excerpt':string,'source_type':{'enum':['SUBJECT','THIRD_PARTY','AI_INFERENCE','OBJECTIVE','CALIBRATION']},'temporal_context':string}}
record={**draft,'properties':{**draft['properties'],
 'id':string,'status':{'enum':['pending','confirmed','rejected','stale']},'revision':{'type':'integer','minimum':1},
 'model_version':string,'prompt_version':string,'created_at':string,'updated_at':string,
 'evidence':{'type':'array','items':{'$ref':'#/$defs/source'}},'label':string,'historical':{'type':'boolean'},'source_valid':{'type':'boolean'}}}
record['required']=list(record['properties'])
schema={'$schema':'https://json-schema.org/draft/2020-12/schema','title':'NarrativeOverviewV1','type':'object','additionalProperties':False,
 '$defs':{'source':source,'record':record},'properties':{
 'subject_id':string,'role':{'enum':['owner','reader']},'records':{'type':'array','items':{'$ref':'#/$defs/record'}},
 'source_evidence':{'type':'array','items':{'$ref':'#/$defs/source'}},
 'understandings':{'type':'array','items':{'type':'object','required':['statement','context','status','evidence','counter_evidence','independent_events','label'],'properties':{
 'statement':string,'context':string,'status':string,'label':string,'independent_events':{'type':'integer','minimum':0},
 'evidence':{'type':'array','items':{'$ref':'#/$defs/source'}},'counter_evidence':{'type':'array','items':{'$ref':'#/$defs/source'}}}}},
 'views':{'type':'array','minItems':4,'maxItems':4,'items':{'type':'object','required':['title','records'],'additionalProperties':False,'properties':{'title':string,'records':{'type':'array','items':string}}}},
 'facets':{'type':'array','minItems':8,'maxItems':8,'items':{'type':'object','required':['id','title','count'],'additionalProperties':False,'properties':{'id':{'enum':draft['properties']['facets']['items']['enum']},'title':string,'count':{'type':'integer','minimum':0}}}},
 'style':{'type':'object','required':['enabled','revision'],'additionalProperties':False,'properties':{'enabled':{'type':'boolean'},'revision':{'type':'integer','minimum':0}}},
 'next_question':{'anyOf':[{'type':'null'},{'type':'object','required':['id','text','reason'],'properties':{'id':string,'text':string,'reason':string}}]},'notice':string}}
schema['required']=list(schema['properties'])
(DIR/'narrative-overview-v1.schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
