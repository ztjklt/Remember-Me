import unittest
from pathlib import Path
from tools.a01_eval.prepare import read_docx, isolate

SOURCE = Path('C:/Users/11537/Desktop/陈国梁——测试(1).docx')

class IsolationTests(unittest.TestCase):
    def test_only_spoken_paragraphs_are_input(self):
        paragraphs, audit = read_docx(SOURCE)
        episodes = isolate(paragraphs, audit)
        self.assertEqual([e['paragraph'] for e in episodes], [28,31,34,37,40,43,46,49,52,55])
        self.assertEqual(len(paragraphs), 65)
        self.assertEqual(audit['tracked_insertions'], 0)
        self.assertEqual(audit['tracked_deletions'], 0)
        for e in episodes:
            self.assertNotIn('1950', e['text'])
            self.assertNotIn('2024', e['text'])
            self.assertNotIn('参考：', e['text'])

    def test_revision_or_paragraph_shift_is_rejected(self):
        paragraphs, audit = read_docx(SOURCE)
        for key in ['tracked_insertions', 'tracked_deletions', 'comments']:
            with self.subTest(key=key), self.assertRaises(ValueError):
                isolate(paragraphs, {**audit, key: 1})
        with self.assertRaises(ValueError):
            isolate(paragraphs[1:], audit)

if __name__ == '__main__': unittest.main()
