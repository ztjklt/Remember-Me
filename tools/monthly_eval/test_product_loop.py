"""Benchmark preflight, not model quality tests."""
import pytest
from product_loop import check_qa_scope


def test_qa_accepts_public_grants_with_unavailable_corrected_original():
    protocol={'reader_required_episode_suffixes':[2], 'reader_private_episode_suffixes':[4],
              'reader_unavailable_episode_suffixes':[1]}
    mapping={f'person-{i:02}':{'episode_id':str(i)} for i in [1,2,4]}
    check_qa_scope('person',protocol,mapping,
        [{'episode_id':'2','cloud_processing_allowed':True}],
        [{'episode_id':'1','unavailable':True}], [{'status':'confirmed','episode_id':'4','kind':'correction'}])


@pytest.mark.parametrize('fault',['private_grant','old_source','pending_revision','missing_grant','missing_revision'])
def test_qa_blocks_incorrect_privacy_or_revision_setup(fault):
    protocol={'reader_required_episode_suffixes':[2], 'reader_private_episode_suffixes':[4],
              'reader_unavailable_episode_suffixes':[1]}
    mapping={f'person-{i:02}':{'episode_id':str(i)} for i in [1,2,4]}
    grants=[{'episode_id':'2','cloud_processing_allowed':True}]
    stories=[{'episode_id':'1','unavailable':fault!='old_source'}]
    revisions=[{'status':'pending' if fault=='pending_revision' else 'confirmed','episode_id':'4','kind':'correction'}]
    if fault=='private_grant':grants.append({'episode_id':'4','cloud_processing_allowed':True})
    if fault=='missing_grant':grants=[]
    if fault=='missing_revision':revisions=[]
    with pytest.raises(RuntimeError):check_qa_scope('person',protocol,mapping,grants,stories,revisions)
