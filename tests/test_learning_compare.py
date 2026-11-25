import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from werkzeug.datastructures import FileStorage

from app import app
from common.arithmetic import solve
from math_practice.db import MathDB
from math_practice.learning import build_report, category, targeted
from version_compare import compare_uploads


def upload(name, text):
    return FileStorage(stream=io.BytesIO(text.encode()), filename=name)


def zipped(name, files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        for path, text in files.items():
            z.writestr(path, text)
    stream.seek(0)
    return FileStorage(stream=stream, filename=name)


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = MathDB(str(Path(self.tmp.name) / 'math.db'))
        self.patch = patch('math_practice.routes.db', self.db)
        self.patch.start()
        self.client = app.test_client()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def submit(self, expr, answer):
        return self.client.post('/math/api/submit', json={'items': [{'expr':expr,'answer':answer}]})

    def test_report_session_isolation_and_latest_correction(self):
        self.submit('3+5', '9')
        self.submit('3 + 5', '8')
        self.submit('9-2', '8')
        self.submit('bad input', '0')
        report = self.client.get('/math/api/learning-report').json
        self.assertEqual((report['total'],report['wrong'],report['excluded']), (3,2,1))
        self.assertEqual(report['unresolved'],1)
        self.assertTrue(next(m for m in report['mistakes'] if m['category']=='加法')['resolved'])
        self.assertEqual(app.test_client().get('/math/api/learning-report').json['total'],0)

    def test_targeted_valid_and_no_answers(self):
        self.submit('12÷3','0')
        response = self.client.post('/math/api/targeted',json={'count':10,'category':'除法'})
        self.assertEqual(response.status_code,200)
        qs = response.json['questions']
        self.assertEqual(len(qs),10)
        self.assertEqual(qs[0]['expr'],'12÷3')
        self.assertEqual(len({q['expr'] for q in qs}),10)
        for q in qs:
            self.assertEqual(set(q), {'expr','category','mode'})
            ok, answer = solve(q['expr'])
            self.assertTrue(ok)
            self.assertEqual(answer.denominator,1)
            self.assertEqual(category(q['expr']), '除法')
        items = [{'expr':q['expr'], 'answer':str(solve(q['expr'])[1])} for q in qs]
        self.assertEqual(self.client.post('/math/api/submit',json={'items':items,'source':'targeted'}).json['correct'],10)
        self.assertEqual(self.client.get('/math/api/learning-report').json['unresolved'],0)

    def test_empty_and_validation(self):
        self.assertEqual(self.client.get('/math/api/learning-report').json['accuracy'],0)
        for data in ({'count':True},{'count':21},{'count':2,'category':[]},[],{'count':10}):
            self.assertEqual(self.client.post('/math/api/targeted',json=data).status_code,400)
        self.assertEqual(self.client.get('/math/learning').status_code,200)

    def test_categories_and_priority(self):
        for expr, expected in [('1/2+1/3','分数运算'),('-3+5','负数运算'),('(3+5)×2','括号运算'),('2^3','乘方运算'),('3+5×2','混合运算')]:
            self.assertEqual(category(expr),expected)
        self.submit('1+2','0');self.submit('1+2','0');self.submit('8-2','0')
        report=self.client.get('/math/api/learning-report').json
        self.assertEqual(report['recommendations'][0]['category'],'加法')
        self.assertTrue(report['categories'][0]['sample_small'])

    def test_truncation_and_repeated_error(self):
        self.submit('1+2','0');self.submit('1+2','3');self.submit('1+2','0')
        self.assertEqual(self.client.get('/math/api/learning-report').json['unresolved'],1)
        row=dict(expr='1+2',is_correct=1,user_answer='3',standard='3',created_at='2026-11-25')
        report=build_report([row]*10001)
        self.assertTrue(report['truncated'])
        self.assertEqual(report['total'],10000)


class ComparisonTests(unittest.TestCase):
    def test_identical_line_counts_still_modified(self):
        result=compare_uploads([upload('a.py','x=1\n')],[upload('a.py','x=2\n')])
        self.assertEqual(result['files'][0]['status'],'modified')
        self.assertEqual(result['delta']['code'],0)

    def test_newline_encoding_normalized(self):
        old=FileStorage(stream=io.BytesIO('x=1\r\n'.encode('utf-16')),filename='a.py')
        result=compare_uploads([old],[upload('a.py','x=1\n')])
        self.assertEqual(result['counts']['unchanged'],1)

    def test_zip_roots_add_delete_and_skipped(self):
        result=compare_uploads([zipped('old.zip',{'old-root/src/a.py':'x=1','old-root/src/gone.py':'x=0','old-root/a.xyzunknown':'hello'})],
            [zipped('new.zip',{'new-root/src/a.py':'x=1','new-root/src/new.py':'x=2'})])
        self.assertEqual(result['counts'],dict(added=1,deleted=1,unchanged=1,modified=0))
        self.assertEqual(len(result['before']['skipped']),1)
        self.assertEqual(result['delta']['files'],0)
        self.assertIn('src/a.py', [r['name'] for r in result['files']])

    def test_keep_root_and_same_basename(self):
        result=compare_uploads([upload('old/src/a.py','x=1')],[upload('new/src/a.py','x=1')],False)
        self.assertEqual(result['counts']['added'],1)
        result=compare_uploads([upload('root/one/a.py','x=1'),upload('root/two/a.py','x=2')],
                               [upload('root/one/a.py','x=3'),upload('root/two/a.py','x=2')])
        self.assertEqual(result['counts']['modified'],1)
        self.assertEqual(result['counts']['unchanged'],1)

    def test_normalized_collision_rejected(self):
        with self.assertRaises(ValueError):
            compare_uploads([zipped('a.zip',{'root/a.py':'x=1'}),zipped('b.zip',{'root/a.py':'x=2'})], [upload('a.py','x=3')])

    def test_api_and_page(self):
        client=app.test_client()
        self.assertEqual(client.get('/code-compare').status_code,200)
        self.assertEqual(client.post('/api/compare').status_code,400)
        response=client.post('/api/compare', data={'before':(io.BytesIO(b'x=1'),'a.py'),'after':(io.BytesIO(b'x=2'),'a.py')})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['counts']['modified'],1)

    def test_unsupported_function_difference_is_unknown(self):
        result=compare_uploads([upload('a.js','const x=1;')],[upload('a.js','const x=2;')])
        self.assertIsNone(result['files'][0]['delta']['functions'])


if __name__ == '__main__':
    unittest.main()
