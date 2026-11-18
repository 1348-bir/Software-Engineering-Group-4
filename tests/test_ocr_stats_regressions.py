import io
import unittest
import zipfile
from unittest.mock import patch
from werkzeug.datastructures import FileStorage
from math_practice import ocr
from code_stats import analyze_uploads


class OCRStatsRegressions(unittest.TestCase):
    def test_missing_engine_returns_actionable_error(self):
        from app import app
        with patch.object(ocr, '_check_available', return_value=False):
            response = app.test_client().post('/math/api/ocr', data={
                'image': (io.BytesIO(b'image'), 'sample.png')})
        self.assertEqual(response.status_code, 503)
        self.assertIn('requirements-ocr.txt', response.json['error'])

    def test_modern_ocr_results(self):
        class Modern:
            def predict(self, path):
                return [{'rec_texts': ['３＋５＝８']}]
        with patch.object(ocr, '_check_available', return_value=True), patch.object(ocr, 'get_ocr', return_value=Modern()):
            self.assertEqual(ocr.recognize('sample.png'), '3+5')

    def test_old_ocr_results(self):
        class Legacy:
            def ocr(self, path, cls):
                return [[[[], ('3+5=8', 0.99)]]]
        with patch.object(ocr, '_check_available', return_value=True), patch.object(ocr, 'get_ocr', return_value=Legacy()):
            self.assertEqual(ocr.recognize('sample.png'), '3+5')

    def test_duplicate_paths_not_charged_twice(self):
        uploads = [FileStorage(stream=io.BytesIO(b'x=1'), filename='a.py') for _ in range(2)]
        with patch('code_stats.MAX_TOTAL', 3):
            report = analyze_uploads(uploads)
        self.assertEqual(report['totals']['files'], 1)

    def test_zip_directories_do_not_consume_file_limit(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr('src/', '')
            archive.writestr('src/a.py', 'x=1')
        data.seek(0)
        with patch('code_stats.MAX_FILES', 1):
            self.assertEqual(analyze_uploads([FileStorage(stream=data, filename='a.zip')])['totals']['files'], 1)
