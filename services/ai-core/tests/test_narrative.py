import pytest
from app.narrative import NarrativeInput, NarrativeProvider
from app.errors import AIOutputInvalid

def source():
    return NarrativeInput(materials=[dict(evidence_id='ev1',episode_id='ep1',source_type='SUBJECT',excerpt='那时候我住在杭州。茶还是不加糖。')])

class Chat:
    def complete(self,system,payload):
        return {'records':[{'kind':'story','title':'在杭州的日子','text':'讲述者回忆在杭州生活。',
            'evidence_ids':['e1'],'facets':['EXPERIENCE'],'time_text':'那时候','place_text':'杭州',
            'aliases':[],'same_event':False,'recipient_label':''}]},'test'

def test_resolves_handles_and_keeps_all_eight_facets_available():
    output=NarrativeProvider(Chat()).propose(source())
    assert output['records'][0]['evidence_ids']==['ev1']
    assert output['model_version']=='test'

@pytest.mark.parametrize('mutation',['evidence','time','letter','extra','duplicate_facet','long_alias','person_event'])
def test_rejects_unknown_reference_invented_time_and_generated_letter(mutation):
    class Bad(Chat):
        def complete(self,*args):
            result,version=super().complete(*args);row=result['records'][0]
            if mutation=='evidence': row['evidence_ids']=['unknown']
            if mutation=='time': row['time_text']='2016年'
            if mutation=='letter': row.update(kind='letter',facets=['EXPRESSION'])
            if mutation=='extra': row['personality_score']=99
            if mutation=='duplicate_facet': row['facets']=['EXPERIENCE','EXPERIENCE']
            if mutation=='long_alias': row['aliases']=['那'*121]
            if mutation=='person_event': row.update(kind='person',same_event=True)
            return result,version
    with pytest.raises(AIOutputInvalid): NarrativeProvider(Bad()).propose(source())
