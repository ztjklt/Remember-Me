import pytest
from app.expression import ExpressionInput, ExpressionProvider

class Chat:
    def __init__(self, accepted=True): self.calls=[];self.accepted=accepted
    def complete(self,system,data):
        self.calls.append(data)
        if len(self.calls)==1: return {'text':'他喝茶时不加糖。'},'test'
        return {'same_facts':self.accepted,'no_new_stance':True,'third_person':True},'test'

def test_optional_style_is_checked_separately_and_examples_never_become_facts():
    chat=Chat();result=ExpressionProvider(chat).express(ExpressionInput(answer='他喝茶不放糖。',examples=[{'id':'s1','text':'事情要慢慢来。'}]))
    assert result['status']=='available' and len(chat.calls)==2
    assert chat.calls[1]['original']=='他喝茶不放糖。'
    assert 'examples' not in chat.calls[1]

def test_rejected_style_does_not_replace_the_evidence_answer():
    result=ExpressionProvider(Chat(False)).express(ExpressionInput(answer='他喝茶不放糖。',examples=[{'id':'s1','text':'事情要慢慢来。'}]))
    assert result['status']=='rejected' and result['text']==''

def test_string_true_is_not_a_valid_semantic_check():
    class Bad(Chat):
        def complete(self,*args):
            result,model=super().complete(*args)
            if len(self.calls)==2: result['same_facts']='true'
            return result,model
    result=ExpressionProvider(Bad()).express(ExpressionInput(answer='他不加糖。',examples=[{'id':'s1','text':'慢慢来。'}]))
    assert result['status']=='rejected'
