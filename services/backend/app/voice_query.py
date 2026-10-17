"""History helps elliptical follow-ups, but must not displace a new topic."""
import re

_DEPENDENT=re.compile(r'^(?:(?:那|那么|然后|还有|后来|可是|所以)[，,\s]*)?'
    r'(?:什么时候|几点|为什么|怎么(?:办|样|做)?|多久|多少|哪(?:里|个|次)|谁|呢|这个|那个|这件事|那件事|刚才|再说一遍)')

def retrieval_query(question,history):
    compact=re.sub(r'[，,。？！?!\s]','',question)
    if not history or len(compact)>22 or not _DEPENDENT.match(compact):return question
    previous=history[-1]['question']
    if len(previous)+len(question)>=980:return question
    # This is a retrieval hint only. Original question/history stay separate in the model packet.
    return previous+'；追问：'+question
