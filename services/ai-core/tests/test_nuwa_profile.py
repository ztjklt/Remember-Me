import pytest
from app.profile_proposals import ProfileProposalProvider,ProfileProposalInput,PROMPT_VERSION,BASE_PROMPT_VERSION
from app.errors import AIOutputInvalid


class Chat:
    def __init__(self,replies):self.replies=list(replies);self.calls=[]
    def complete(self,system,payload):
        self.calls.append((system,payload));return self.replies.pop(0),'test-model'


def material():
    return ProfileProposalInput(materials=[{'evidence_id':'real-source','episode_id':'real-episode',
        'excerpt':'当时母亲需要照顾，我没有去外地工作。我没有说今后一定不离开。'}])


def candidate(statement='讲述者当时选择留下照顾母亲'):
    return {'domain':'DECISION_PATTERNS','kind':'trait','statement':statement,
        'context':'仅限母亲当时需要照顾的那次选择，不代表今后一定不离开',
        'evidence_ids':['s1'],'counter_evidence_ids':[]}


def test_nuwa_keeps_conditional_candidate_pending_contract_and_checks_support():
    chat=Chat([{'candidates':[candidate()]},{'checks':[{'candidate':1,'supported':True,'bounded':True,'counter_correct':True}]}])
    output=ProfileProposalProvider(chat).propose(material())
    assert output.prompt_version==PROMPT_VERSION
    assert output.candidates[0].evidence_ids==['real-source']
    assert 'context' in output.candidates[0].model_dump()
    assert len(chat.calls)==2
    assert '不同录音编号不等于独立事件' in chat.calls[0][0]


def test_baseline_is_available_for_same_material_comparison_without_review():
    chat=Chat([{'candidates':[candidate()]}])
    output=ProfileProposalProvider(chat,method='baseline').propose(material())
    assert output.prompt_version==BASE_PROMPT_VERSION and len(chat.calls)==1


def test_unsupported_or_overgeneralized_candidate_is_not_saved_as_understanding():
    chat=Chat([{'candidates':[candidate('讲述者永远不会离开家乡')]},
        {'checks':[{'candidate':1,'supported':False,'bounded':False,'counter_correct':True}]}])
    assert ProfileProposalProvider(chat).propose(material()).candidates==[]


@pytest.mark.parametrize('reply',[{'checks':[]},{'checks':[{'candidate':1,'supported':'true','bounded':True,'counter_correct':True}]}])
def test_missing_or_non_boolean_review_fails_instead_of_publishing(reply):
    chat=Chat([{'candidates':[candidate()]},reply])
    with pytest.raises(AIOutputInvalid):ProfileProposalProvider(chat).propose(material())


def test_forged_sources_are_rejected_before_semantic_review():
    c=candidate();c['evidence_ids']=['invented']
    chat=Chat([{'candidates':[c]}])
    with pytest.raises(AIOutputInvalid):ProfileProposalProvider(chat).propose(material())
    assert len(chat.calls)==1
