import io
import unittest
from unittest.mock import patch
from math_practice import ocr
from app import app


class PageOCR(unittest.TestCase):
    def test_uncertain_symbols_are_retained_and_flagged(self):
        expressions=ocr._page_candidates(['10.6=', '108=', '15-7n', '5+4-', '姓名', '一年级(4)'])
        self.assertEqual(expressions,['10.6','108','15-7n','5+4-'])
        self.assertTrue(all(ocr.needs_review(expr) for expr in expressions))
        self.assertFalse(ocr.needs_review('10+8'))

    def test_partial_success_uses_second_pass(self):
        with patch.object(ocr,'_check_available',return_value=True), patch.object(ocr,'_prepare',return_value='x'), patch.object(ocr,'get_ocr'), patch.object(ocr,'_texts_from',side_effect=[['10.6=','108='],['10-6=','10+8=']]):
            self.assertEqual(ocr.recognize_page('x'),['10-6','10+8'])

    def test_five_questions_remain_separate_including_duplicate(self):
        lines=['1. 3+5=', '2、6×2=', '3. (8-2)÷3=', '4. 10-1=', '5. 3+5=']
        with patch.object(ocr,'_check_available',return_value=True), patch.object(ocr,'_prepare',return_value='x'), patch.object(ocr,'get_ocr'), patch.object(ocr,'_texts_from',return_value=lines):
            self.assertEqual(ocr.recognize_page('x'), ['3+5','6×2','(8-2)÷3','10-1','3+5'])

    def test_heading_not_merged_and_inline_questions_split(self):
        lines=['第1页 共5道题', '1. 3+5=  2. 7-2=', '3. (1+2)=', '班级三年级']
        with patch.object(ocr,'_check_available',return_value=True), patch.object(ocr,'_prepare',return_value='x'), patch.object(ocr,'get_ocr'), patch.object(ocr,'_texts_from',return_value=lines):
            self.assertEqual(ocr.recognize_page('x'), ['3+5','7-2','(1+2)'])

    def test_recognition_does_not_reveal_answers_or_write_history(self):
        with patch.object(ocr,'recognize_page',return_value=['1+2']*5), patch('math_practice.routes.db.add_attempt') as save:
            response=app.test_client().post('/math/api/ocr-page',data={'image':(io.BytesIO(b'image'),'sheet.png')})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json,{'count':5,'questions':[{'expr':'1+2'}]*5})
        save.assert_not_called()

    def test_missing_image(self):
        self.assertEqual(app.test_client().post('/math/api/ocr-page').status_code,400)
