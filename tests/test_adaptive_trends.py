import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from app import app
from common.arithmetic import solve
from math_practice.adaptive import choose_level, generate_adaptive, CATEGORIES
from math_practice.learning import category
from math_practice.trends import build_trends
from math_practice.db import MathDB


def attempt(expr='2+3', correct=True, source='manual', when='2026-11-25 12:00:00'):
    return dict(expr=expr, is_correct=int(correct), source=source, created_at=when,
                standard='5', user_answer='5' if correct else '0')


class AdaptiveTests(unittest.TestCase):
    def test_sample_threshold_and_no_request_only_level_inflation(self):
        rows=[attempt(source='adaptive:加法:2')]*4
        self.assertEqual(choose_level(rows,'加法')['level'],2)
        rows.append(attempt(source='adaptive:加法:2'))
        self.assertEqual(choose_level(rows,'加法')['level'],3)
        self.assertEqual(choose_level(rows,'加法')['level'],3)
        self.assertEqual(choose_level([],'加法')['level'],1)

    def test_demotion_and_category_isolation(self):
        rows=[attempt(correct=False,source='adaptive:加法:3')]*5
        self.assertEqual(choose_level(rows,'加法')['level'],2)
        self.assertEqual(choose_level(rows,'除法')['level'],1)
        self.assertEqual(choose_level(rows)['category'],'加法')
        self.assertEqual(choose_level([attempt('1/2+1/3')])['category'],'分数运算')

    def test_boundary_rates(self):
        rows=[attempt(source='adaptive:加法:2')]*17+[attempt(correct=False,source='adaptive:加法:2')]*3
        self.assertEqual(choose_level(rows,'加法')['level'],3)
        rows=[attempt(source='adaptive:加法:2')]*12+[attempt(correct=False,source='adaptive:加法:2')]*8
        self.assertEqual(choose_level(rows,'加法')['level'],2)

    def test_generated_questions_match_category_valid_and_hide_answers(self):
        examples={'加法':'2+3','减法':'8-2','乘法':'2×3','除法':'8÷2','混合运算':'2+3×4','括号运算':'(2+3)×4','负数运算':'-2+3','分数运算':'1/2+1/3','乘方运算':'2^3'}
        for kind in CATEGORIES:
            for level in range(1,5):
                with self.subTest(kind=kind,level=level):
                    # Correctness of 80% keeps the requested tier unchanged.
                    rows=[attempt(examples[kind], i<4,f'adaptive:{kind}:{level}') for i in range(5)]
                    result=generate_adaptive(rows,10,kind)
                    self.assertEqual(result['decision']['level'],level)
                    self.assertEqual(result['count'],10)
                    self.assertEqual(len({q['expr'] for q in result['questions']}),10)
                    for q in result['questions']:
                        self.assertTrue(solve(q['expr'])[0])
                        self.assertEqual(category(q['expr']),kind)
                        self.assertEqual(set(q),{'expr','category','level'})


class TrendTests(unittest.TestCase):
    def test_windows_correction_and_no_activity(self):
        today=date(2026,11,25)
        rows=[attempt(when='2026-11-25 12:00:00'),attempt(correct=False,when='2026-11-24 12:00:00'),
              attempt(correct=False,when='2026-11-18 12:00:00'),attempt(when='2026-11-12 12:00:00')]
        t=build_trends(rows,today)
        self.assertEqual(t['current']['total'],2)
        self.assertEqual(t['previous']['total'],2)
        self.assertEqual(t['accuracy_change_pp'],0)
        self.assertEqual(t['current']['correction_rate'],1)
        self.assertEqual(t['current']['corrected'],1)
        self.assertIsNone(t['days'][1]['accuracy'])
        self.assertEqual(t['days'][-1]['accuracy'],1)
        self.assertEqual(t['current']['active_days'],2)

    def test_invalid_future_and_date_exclusions(self):
        t=build_trends([attempt(expr='bad'),attempt(when='bad'),attempt(when='2026-11-26')],date(2026,11,25))
        self.assertEqual(t['excluded_dates'],2)
        self.assertEqual(t['current']['total'],0)
        self.assertIsNone(t['accuracy_change_pp'])
        self.assertIsNone(t['current']['correction_rate'])


class AdaptiveApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=MathDB(str(Path(self.tmp.name)/'math.db'))
        self.patch=patch('math_practice.routes.db',self.db);self.patch.start()
        self.client=app.test_client()

    def tearDown(self):
        self.patch.stop();self.tmp.cleanup()

    def test_api_evidence_isolation_and_persistent_cookie(self):
        r=self.client.post('/math/api/adaptive',json={'count':5,'category':'加法'})
        self.assertEqual(r.status_code,200)
        self.assertIn('Expires=',r.headers.get('Set-Cookie',''))
        self.assertEqual(r.json['decision']['level'],1)
        items=[dict(expr=q['expr'],answer=str(solve(q['expr'])[1])) for q in r.json['questions']]
        self.client.post('/math/api/submit',json={'items':items,'source':r.json['source']})
        self.assertEqual(self.client.post('/math/api/adaptive',json={'category':'加法'}).json['decision']['level'],2)
        self.assertEqual(app.test_client().post('/math/api/adaptive',json={'category':'加法'}).json['decision']['level'],1)
        report=self.client.get('/math/api/learning-report').json
        self.assertEqual(report['trends']['current']['total'],5)
        self.assertEqual(report['trends']['current']['accuracy'],1)
        self.assertTrue(self.db.recent_attempts(limit=1)[0]['source'].startswith('adaptive:'))

    def test_validation_and_pages(self):
        for body in ([],{'count':True},{'count':51},{'category':'bad'},{'category':[]}):
            self.assertEqual(self.client.post('/math/api/adaptive',json=body).status_code,400)
        page=self.client.get('/math/').get_data(as_text=True)
        self.assertIn('自适应难度',page)
        self.assertIn('/static/practice-draft.js',page)
        self.assertIn('学习趋势报告',self.client.get('/math/learning').get_data(as_text=True))


if __name__=='__main__':
    unittest.main()
