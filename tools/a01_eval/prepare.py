"""Read-only DOCX split. Reference data is never loaded by run_baseline.py."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'evaluations/a01-20261012'
SOURCE = Path('C:/Users/11537/Desktop/陈国梁——测试(1).docx')
ALLOWED = (28,31,34,37,40,43,46,49,52,55)
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

def digest(data): return hashlib.sha256(data).hexdigest()

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)

def read_docx(path):
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
        paragraphs = [''.join(n.text or '' for n in p.findall('.//w:t', NS))
                      for p in root.findall('./w:body/w:p', NS)]
        audit = {'source_sha256': digest(path.read_bytes()), 'paragraph_count': len(paragraphs),
                 'character_count': sum(map(len, paragraphs)),
                 'tracked_insertions': len(root.findall('.//w:ins', NS)),
                 'tracked_deletions': len(root.findall('.//w:del', NS)),
                 'comments': len(root.findall('.//w:commentReference', NS)),
                 'comment_parts': [name for name in archive.namelist() if 'comments' in name.lower()]}
    return paragraphs, audit

def isolate(paragraphs, audit):
    if len(paragraphs) != 65 or any(audit[k] for k in ('tracked_insertions','tracked_deletions','comments','comment_parts')):
        raise ValueError('Changed source structure or review markup needs explicit review')
    if '虚构' not in paragraphs[0] or '不交给建模系统' not in paragraphs[2] or '仅测试人员' not in paragraphs[55]:
        raise ValueError('DOCX section boundaries changed')
    episodes = []
    for i, paragraph in enumerate(ALLOWED, 1):
        if not paragraphs[paragraph-3].startswith(f'录音 {i:02}'):
            raise ValueError('Recording boundary changed')
        text = paragraphs[paragraph-1]
        if any(token in text for token in ('1950','2024','参考：')):
            raise ValueError('Forbidden reference token in spoken input')
        episodes.append({'id': f'A01_{i:02}', 'paragraph': paragraph, 'text': text,
                         'sha256': digest(text.encode('utf-8')), 'input_type': 'spoken_script_text_not_ASR'})
    return episodes

def main():
    paragraphs, audit = read_docx(SOURCE)
    episodes = isolate(paragraphs, audit)
    save(DATA / 'input/episodes.json', episodes)
    save(DATA / 'manifest.json', {**audit, 'fiction': True, 'source_path': str(SOURCE),
        'allowed_paragraphs': ALLOWED, 'input_sha256': digest((DATA/'input/episodes.json').read_bytes()),
        'excluded_paragraphs': [n for n in range(1,66) if n not in ALLOWED],
        'batches': [['A01_01','A01_02','A01_03','A01_04'], ['A01_05','A01_06','A01_07'], ['A01_08','A01_09','A01_10']]})
    questions = []
    for i in range(57,65):
        question, answer = paragraphs[i-1].split('参考：',1)
        questions.append({'id':f'Q{i-56:02}', 'question':question.removeprefix('问：').strip(),
                          'reference': answer, 'reference_paragraph': i})
    save(DATA / 'input/questions.json', [{'id':q['id'],'question':q['question']} for q in questions] + [
        {'id':'U01','question':'讲述者确切哪一年出生？'},
        {'id':'U02','question':'讲述者确切哪一年确诊阿尔茨海默病？'},
        {'id':'A01','question':'第一次见面时是谁觉得谁老实？这是直接听到当事人说，还是讲述者转述？'},
        {'id':'N01','question':'讲述者一开始责怪桂芳动了钥匙，资料能否证明桂芳真的动了他的东西？'}])
    save(DATA / 'reference-only/gold.json', {'original_questions':questions,
        'hidden_truth_never_model_input':{'birth_year':1950,'diagnosis_year':2024},
        'unknown_checks':['exact_birth_year','exact_diagnosis_year','first_meeting_weekday'],
        'full_paragraphs':[{'paragraph':i,'text':p} for i,p in enumerate(paragraphs,1)]})
    print(json.dumps({'paragraphs':len(paragraphs),'characters':audit['character_count'],
        'spoken_episodes':len(episodes),'spoken_characters':sum(len(e['text']) for e in episodes),
        'tracked_changes':audit['tracked_insertions']+audit['tracked_deletions'],'comments':audit['comments']}, ensure_ascii=False))

if __name__ == '__main__': main()
