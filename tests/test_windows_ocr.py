import subprocess
import unittest
from unittest.mock import patch
from math_practice import ocr


class WindowsOCR(unittest.TestCase):
    def test_page_fallback_preserves_separate_and_duplicate_questions(self):
        with patch.object(ocr, '_check_available', return_value=False), patch.object(ocr.os, 'name', 'nt'), patch.object(ocr, '_windows_lines', return_value=['3+5=', '6-2=', '3+5=']):
            self.assertEqual(ocr.recognize_page('image.png'), ['3+5', '6-2', '3+5'])

    def test_page_engine_failure_also_falls_back(self):
        with patch.object(ocr, '_check_available', return_value=True), patch.object(ocr.os, 'name', 'nt'), patch.object(ocr, '_paddle_page', side_effect=RuntimeError), patch.object(ocr, '_windows_lines', return_value=['6÷2=']):
            self.assertEqual(ocr.recognize_page('image.png'), ['6÷2'])

    def test_native_page_does_not_fuse_inline_questions(self):
        with patch.object(ocr, '_check_available', return_value=False), patch.object(ocr.os, 'name', 'nt'), patch.object(ocr, '_windows_lines', return_value=['3+5= 6-2=']):
            with self.assertRaisesRegex(RuntimeError, 'Windows OCR'):
                ocr.recognize_page('image.png')

    def test_missing_paddle_uses_native_engine(self):
        with patch.object(ocr, '_check_available', return_value=False), patch.object(ocr.os, 'name', 'nt'), patch.object(ocr, '_windows_lines', return_value=['３＋５＝８']):
            self.assertEqual(ocr.recognize('image.png'), '3+5')

    def test_broken_paddle_falls_back_to_windows(self):
        with patch.object(ocr, '_check_available', return_value=True), patch.object(ocr.os, 'name', 'nt'), patch.object(ocr, '_paddle_lines', side_effect=RuntimeError), patch.object(ocr, '_windows_lines', return_value=['6 ÷ 2 = 3']):
            self.assertEqual(ocr.recognize('image.png'), '6÷2')

    def test_multiple_questions_not_silently_combined(self):
        with patch.object(ocr, '_check_available', return_value=False), patch.object(ocr.os, 'name', 'nt'), patch.object(ocr, '_windows_lines', return_value=['1+2', '3+4']):
            with self.assertRaises(RuntimeError):
                ocr.recognize('image.png')

    def test_timeout_has_actionable_error(self):
        with patch.object(ocr.subprocess, 'run', side_effect=subprocess.TimeoutExpired('powershell', 30)):
            with self.assertRaisesRegex(RuntimeError, 'Windows OCR'):
                ocr._windows_lines('image.png')
