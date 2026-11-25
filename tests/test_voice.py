import unittest
from app import app
from math_practice.voice import parse_spoken


class VoiceQuestions(unittest.TestCase):
    def test_chinese_multiple_questions(self):
        data=parse_spoken('第一题三加五，第二题十二减六，第三题七乘以八，第四题二十四除以六等于多少')
        self.assertEqual([q['expr'] for q in data['questions']],['3+5','12-6','7×8','24÷6'])
        self.assertEqual(data['unrecognized'],[])

    def test_numbers_brackets_duplicates(self):
        data=parse_spoken('左括号一百零三减三右括号除以十。三加五。三加五')
        self.assertEqual([q['expr'] for q in data['questions']],['(103-3)÷10','3+5','3+5'])

    def test_unknown_word_problem_is_reported(self):
        data=parse_spoken('小明有三个苹果，三点五加二')
        self.assertEqual(data['count'],0)
        self.assertEqual(len(data['unrecognized']),2)

    def test_api_does_not_return_answers(self):
        response=app.test_client().post('/math/api/voice-questions',json={'text':'三加五'})
        self.assertEqual(response.status_code,200)
        self.assertNotIn('standard',response.get_data(as_text=True))
        self.assertEqual(response.json['questions'][0]['expr'],'3+5')
        self.assertEqual(app.test_client().post('/math/api/voice-questions',json={'text':None}).status_code,400)

    def test_page_and_project_entry(self):
        response=app.test_client().get('/math/voice')
        self.assertEqual(response.status_code,200)
        self.assertIn('开始说题',response.get_data(as_text=True))
        self.assertIn('/math/voice',app.test_client().get('/math').get_data(as_text=True))

    def test_spoken_variants_mixed_numbers_and_fullwidth(self):
        cases={
            '三加\n五':['3+5'],
            '三\n加五':['3+5'],
            '第一题三加五第二题十减六':['3+5','10-6'],
            '１２加六':['12+6'],
            '1百零2减二':['102-2'],
            '两百零三减去三':['203-3'],
            '负五加上二':['-5+2'],
            '六乘上七':['6×7'],
            '十二减掉三':['12-3'],
            '幺加一':['1+1'],
        }
        for spoken,expected in cases.items():
            with self.subTest(spoken=spoken):
                data=parse_spoken(spoken)
                self.assertEqual([q['expr'] for q in data['questions']],expected)

    def test_ambiguous_short_number_not_guessed(self):
        data=parse_spoken('一百二加三')
        self.assertEqual(data['count'],0)
        self.assertEqual(data['unrecognized'],['一百二加三'])
