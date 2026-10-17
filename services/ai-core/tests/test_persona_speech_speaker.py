"""A literal speaker swap is invalid even if a model reviewer would accept it."""
import pytest
from app.persona import PersonaInput, PersonaValidationInvalid, _packet, _render


def render(text, sources):
    data=PersonaInput.model_validate(dict(question='那次你怎么回答的？',voice_response=True,
        understandings=[],examples=[],contributions=[],candidates=[dict(memory_item_id='m',statement='原始记录',traits=[],
            evidence=[dict(evidence_id=f'e{i}',excerpt=s,source_type='SUBJECT') for i,s in enumerate(sources,1)])]))
    point=dict(question_part=data.question,mode='FACT',text=text,source_ids=[f's{i}' for i in range(1,len(sources)+1)],
               understanding_ids=[],contribution_ids=[],names=[])
    return _render({'points':[point]},*_packet(data),'test')


@pytest.mark.parametrize('text,sources',[
    ('你说今天先休息。',['我说今天先休息。']),
    ('你说再煮就软了，你回我“对呀，我就想吃软一点”。我就把自己的先盛了，你那份留在锅里。',
     ['她有一回来吃面，让我多煮一会儿。','我说再煮就软了。','她说，对呀，我就想吃软一点。','我把自己的先盛了，她那份留锅里。']),
])
def test_literal_subject_speech_cannot_be_reassigned_to_listener(text,sources):
    with pytest.raises(PersonaValidationInvalid) as caught:render(text,sources)
    assert caught.value.diagnostic['category']=='speech_speaker_mismatch'


@pytest.mark.parametrize('text,sources',[
    ('我说今天先休息。',['我说今天先休息。']),
    ('你说今天先休息。',['她说今天先休息。']),
    ('你说今天先休息。',['我说今天先休息。','她说今天先休息。']),
    ('你说：“我说今天先休息。”',['她说：“我说今天先休息。”']),
])
def test_guard_preserves_correct_or_ambiguous_speakers_for_semantic_review(text,sources):
    assert render(text,sources)[0].answer==text
