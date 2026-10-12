import pytest
from app.profile_proposals import ProfileCandidate, Material
from app.profile_review import review_candidates
from app.errors import AIOutputInvalid


def candidates():
    return [ProfileCandidate(domain='RELATIONSHIPS',kind='trait',statement='桂芳年轻时上夜班。',
        context='回顾年轻生活',evidence_ids=['ep8'],counter_evidence_ids=[]),
        ProfileCandidate(domain='RELATIONSHIPS',kind='trait',statement='讲述者年轻时上夜班，桂芳带孩子。',
        context='回顾年轻生活',evidence_ids=['ep8'],counter_evidence_ids=[])]


def row(index,ok):
    return dict(index=index,supported=ok,attribution=ok,qualifiers=True,context_complete=True,reason='核对原文主语')


def test_role_swap_review_removes_only_rejected_candidate_without_rewriting():
    items=candidates()
    class Chat:
        def complete(self,system,payload):
            assert payload['materials'][0]['excerpt']=='我年轻时上夜班，你一个人带两个孩子。'
            assert payload['candidates'][0]['statement']=='桂芳年轻时上夜班。'
            return {'reviews':[row(1,True),row(0,False)]},'model'
    result=review_candidates(Chat(),items,[Material(evidence_id='ep8',episode_id='8',excerpt='我年轻时上夜班，你一个人带两个孩子。')])
    assert result==[items[1]] and result[0] is items[1]


@pytest.mark.parametrize('reviews', [[row(0,True)], [row(0,True),row(0,True)],
    [dict(row(0,True),attribution='true'),row(1,True)]])
def test_incomplete_duplicate_or_non_boolean_reviews_fail_closed(reviews):
    class Chat:
        def complete(self,*args): return {'reviews':reviews},'model'
    with pytest.raises(AIOutputInvalid):review_candidates(Chat(),candidates(),[])


def test_empty_profile_does_not_dispatch_review():
    assert review_candidates(object(),[],[])==[]


def test_model_audit_cannot_approve_unstated_fault_judgement():
    item=candidates()[0].model_copy(update={'statement':'讲述者错怪了桂芳。'})
    class Chat:
        def complete(self,*args):return {'reviews':[row(0,True)]},'model'
    original=Material(evidence_id='ep8',episode_id='8',excerpt='我跟桂芳发脾气，说她动我东西。')
    assert review_candidates(Chat(),[item],[original])==[]
    # Explicit self-correction can support that word; do not prohibit the word.
    corrected=original.model_copy(update={'excerpt':'后来我知道是自己放错了，我错怪了桂芳。'})
    assert review_candidates(Chat(),[item],[corrected])==[item]
