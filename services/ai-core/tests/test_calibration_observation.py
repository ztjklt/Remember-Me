"""Protocol checks for source observations; scripted outputs are not semantic QA."""
from copy import deepcopy

import pytest

from app.calibration import CalibrationInput, CalibrationOutput
from app.errors import AIOutputInvalid
from app.providers.weixin import WeixinCalibrationProvider
from test_calibration import _provider


def material():
    return CalibrationInput(question='旧台灯坏了，你会怎样考虑？',
        locked_answer='我会心疼钱，大概先看看能不能修。',
        human_answer='普通小毛病我愿意先看看原因。省钱是省钱，不能为了省这点钱让人冒险。这是我现在想清楚的界限。')


def comparison():
    return {'summary':'本人补充了安全条件，不能据此判断本人情绪。', 'suggested_question':None,
        'dimensions':[
            {'dimension':'DECISION','alignment':'PARTIAL','note':'本人补充区分了小毛病。','human_excerpt':'普通小毛病我愿意先看看原因。'},
            {'dimension':'REASONING','alignment':'PARTIAL','note':'本人补充说明避免冒险的理由。','human_excerpt':'不能为了省这点钱让人冒险'},
            {'dimension':'VALUE_PRIORITY','alignment':'DIFFERENT','note':'本人补充强调安全条件优先。','human_excerpt':'不能为了省这点钱让人冒险'},
            {'dimension':'EMOTIONAL_REACTION','alignment':'NOT_OBSERVED','note':'本人补充没有直接自述情绪，无法比较。','human_excerpt':None},
            {'dimension':'EXPRESSION','alignment':'PARTIAL','note':'本人补充用条件句进一步说明边界。','human_excerpt':'这是我现在想清楚的界限。'},
        ]}


def weixin(raw):
    provider=WeixinCalibrationProvider(api_key='test-only')
    captured=[]
    def complete(system,payload):
        captured.append((system,payload))
        return deepcopy(raw),'Deepseek-v4-flash'
    provider.complete=complete
    return provider,captured


def test_no_emotion_observation_preserves_other_dimensions_and_old_contract():
    provider,captured=weixin(comparison())
    try: output=provider.compare(material())
    finally: provider.close()
    emotion=next(d for d in output.dimensions if d.dimension=='EMOTIONAL_REACTION')
    assert emotion.alignment=='NOT_OBSERVED' and emotion.human_excerpt is None
    assert [d.alignment for d in output.dimensions]==['PARTIAL','PARTIAL','DIFFERENT','NOT_OBSERVED','PARTIAL']
    assert set(output.model_dump())=={'summary','dimensions','suggested_question','model_version'}
    assert captured[0][1]==material().model_dump()
    from app.calibration import PROMPT_VERSION,SYSTEM
    assert PROMPT_VERSION=='calibration-source-comparison-v2' and SYSTEM.startswith(PROMPT_VERSION)
    assert provider.prompt_version==PROMPT_VERSION
    assert '真人' not in SYSTEM
    assert '不能从书面语气' in SYSTEM and 'NOT_OBSERVED' in SYSTEM
    assert '心理状态' in SYSTEM and '本人补充' in SYSTEM


@pytest.mark.parametrize('alignment',['MATCH','PARTIAL','DIFFERENT'])
def test_explicit_emotion_self_report_is_not_globally_suppressed(alignment):
    data=material().model_copy(update={'human_answer':material().human_answer+'我看到火花时有点害怕。'})
    raw=comparison()
    raw['dimensions'][3].update(alignment=alignment,note='本人补充明确自述了看到火花时的害怕。',human_excerpt='我看到火花时有点害怕。')
    provider,_=weixin(raw)
    try: output=provider.compare(data)
    finally: provider.close()
    assert output.dimensions[3].alignment==alignment
    assert output.dimensions[3].human_excerpt=='我看到火花时有点害怕。'


@pytest.mark.parametrize('backend',['weixin','deepseek'])
@pytest.mark.parametrize('bad',['missing','blank','locked_only','unobserved_quote'])
def test_invalid_emotion_evidence_is_rejected_by_both_providers(backend,bad):
    raw=comparison(); emotion=raw['dimensions'][3]
    emotion.update(alignment='PARTIAL',note='不应通过。')
    emotion['human_excerpt']={'missing':None,'blank':' ', 'locked_only':'我会心疼钱',
        'unobserved_quote':'这是我现在想清楚的界限。'}[bad]
    if bad=='unobserved_quote': emotion['alignment']='NOT_OBSERVED'
    data=material().model_copy(update={'human_answer':material().human_answer+' '})
    provider,_=weixin(raw) if backend=='weixin' else _provider(raw)
    try:
        with pytest.raises(AIOutputInvalid): provider.compare(data)
    finally: provider.close()


def test_whitespace_only_note_cannot_masquerade_as_an_observation_explanation():
    from pydantic import ValidationError
    raw=comparison(); raw['dimensions'][3]['note']=' \n '
    with pytest.raises(ValidationError): CalibrationOutput.model_validate(raw|{'model_version':'test'})
