import io
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from contextlib import closing
from pathlib import Path
from werkzeug.datastructures import FileStorage
from code_stats import count_source, count_stream, analyze_uploads, MAX_FILE, MAX_TOTAL, MAX_UPLOAD, MAX_REQUEST
from safe_math import evaluate
import math_app
from app import app


def upload(name, data):
    return FileStorage(stream=io.BytesIO(data), filename=name)


class SourceCounts(unittest.TestCase):
    def test_python_strings_and_inline_comments(self):
        r = count_source('demo.py', b'# heading\nx = "# string" # inline\n\nprint(x)\n')
        self.assertEqual([r[k] for k in ('total', 'code', 'comment', 'blank', 'comment_any')], [4, 2, 1, 1, 2])

    def test_javascript_block_comments_and_url(self):
        r = count_source('demo.js', b'// header\nconst url = "https://example.com";\n/* start\n\nend */\nconsole.log(url); // note\n')
        self.assertEqual([r[k] for k in ('total', 'code', 'comment', 'blank', 'comment_any')], [6, 2, 3, 1, 4])

    def test_common_languages(self):
        samples = {
            'demo.java': '// c\nclass Demo {}\n',
            'demo.go': '// c\npackage main\n',
            'demo.rs': '// c\nfn main() {}\n',
            'demo.cs': '// c\nclass Demo {}\n',
            'demo.sql': '-- c\nSELECT 1;\n',
            'demo.html': '<!-- c -->\n<p>Hello</p>\n',
            'demo.css': '/* c */\na {color: red;}\n',
            'demo.sh': '# c\necho hi\n',
            'demo.rb': '# c\nputs "hi"\n',
            'demo.ts': '// c\nconst x: number = 1;\n',
        }
        for name, source in samples.items():
            with self.subTest(name=name):
                r = count_source(name, source.encode())
                self.assertEqual((r['code'], r['comment'], r['total']), (1, 1, 2))

    def test_cpp_preprocessor(self):
        r = count_source('demo.cpp', b'#include <stdio.h>\n#define COUNT 4\n// c\nint x = 1; /* c */\n')
        self.assertEqual((r['code'], r['comment'], r['comment_any']), (3, 1, 2))

    def test_empty_newlines_and_document_strings(self):
        for data, expected in [(b'', 0), (b'x=1', 1), (b'x=1\n', 1), (b'\n', 1), (b'x=1\r\n\r\n', 2)]:
            with self.subTest(data=data):
                r = count_source('demo.py', data)
                self.assertEqual(r['total'], expected)
                self.assertEqual(r['total'], r['code'] + r['comment'] + r['blank'])
        r = count_source('demo.py', b'"""doc\nstring"""\n')
        self.assertEqual((r['code'], r['comment']), (2, 0))

    def test_encodings(self):
        for encoding in ('utf-8-sig', 'utf-16', 'gb18030'):
            with self.subTest(encoding=encoding):
                r = count_source('demo.py', '# 中文注释\nx=1\n'.encode(encoding))
                self.assertEqual((r['code'], r['comment']), (1, 1))

    def test_unknown_binary_and_large(self):
        for name, data in [('demo.unknownxyz', b'hi'), ('binary.py', b'\x00\x01')]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                count_source(name, data)

    def test_file_size_boundary_before_reading(self):
        with patch('code_stats.MAX_FILE', 64):
            self.assertEqual(count_source('a.py', b'#' + b' ' * 63)['bytes'], 64)
            with self.assertRaisesRegex(ValueError, '1 GB'):
                count_source('a.py', b' ' * 65)
        stream = unittest.mock.Mock()
        with self.assertRaisesRegex(ValueError, '1 GB'):
            count_stream('a.py', stream, MAX_FILE + 1)
        stream.read.assert_not_called()

    def test_one_gb_configuration(self):
        self.assertEqual((MAX_FILE, MAX_TOTAL, MAX_UPLOAD), (1024 ** 3,) * 3)
        self.assertEqual(app.config['MAX_CONTENT_LENGTH'], MAX_REQUEST)
        self.assertGreater(MAX_REQUEST, MAX_UPLOAD)

    def test_chunk_boundaries_and_bounded_reads(self):
        class ChunkedStream(io.BytesIO):
            def read(self, size=-1):
                if size < 0 or size > 2:
                    raise AssertionError('Unexpected unbounded read')
                return super().read(size)
        for encoding in ('utf-8-sig', 'utf-16', 'gb18030'):
            data = '# 中文\r\nx="中文" # 注释\r\n\r\n'.encode(encoding)
            with self.subTest(encoding=encoding), patch('code_stats.READ_CHUNK', 1):
                row = count_stream('a.py', ChunkedStream(data), len(data))
                self.assertEqual([row[k] for k in ('total', 'code', 'comment', 'blank', 'comment_any')], [3, 1, 1, 1, 2])

    def test_uploaded_total_boundary(self):
        with patch('code_stats.MAX_UPLOAD', 64):
            r = analyze_uploads([upload('a.py', b'#' + b' ' * 63)])
            self.assertEqual(r['totals']['files'], 1)
            with self.assertRaisesRegex(ValueError, '上传文件总大小超过 1 GB'):
                analyze_uploads([upload('a.py', b' ' * 33), upload('b.py', b' ' * 32)])

    def test_decompressed_boundary(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('a.py', '#' + ' ' * 63)
        with patch('code_stats.MAX_TOTAL', 64):
            self.assertEqual(analyze_uploads([upload('a.zip', stream.getvalue())])['totals']['files'], 1)
        with patch('code_stats.MAX_TOTAL', 63), self.assertRaisesRegex(ValueError, '解压后的总大小超过 1 GB'):
            analyze_uploads([upload('a.zip', stream.getvalue())])

    def test_zip_ignore_paths_and_unknown_files(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            z.writestr('src/demo.py', '# note\nx=1\n')
            z.writestr('node_modules/pkg/a.js', 'let x=1')
            z.writestr('../outside.py', 'x=1')
            z.writestr('image.png', b'\x00\x01')
        r = analyze_uploads([upload('project.zip', stream.getvalue())])
        self.assertEqual((r['totals']['files'], r['totals']['skipped']), (1, 3))
        self.assertEqual(r['files'][0]['name'], 'project.zip/src/demo.py')

    def test_corrupt_archive(self):
        with self.assertRaises(ValueError):
            analyze_uploads([upload('broken.zip', b'not zip')])

    def test_duplicate_files(self):
        r = analyze_uploads([upload('a.py', b'x=1'), upload('a.py', b'x=2')])
        self.assertEqual((r['totals']['files'], r['totals']['skipped']), (1, 1))


class WebsiteFlows(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_database = math_app.DATABASE
        math_app.DATABASE = str(Path(self.temp.name) / 'test.db')
        math_app.init_db()
        app.config.update(TESTING=True, SECRET_KEY='test-only')
        self.client = app.test_client()

    def tearDown(self):
        math_app.DATABASE = self.old_database
        self.temp.cleanup()

    def history_count(self):
        with closing(sqlite3.connect(math_app.DATABASE)) as conn:
            return conn.execute('SELECT COUNT(*) FROM history').fetchone()[0]

    def test_all_pages(self):
        for page in ['/', '/code-stats', '/math', '/arithmetic', '/game24', '/history', '/game24/solution', '/static/style.css', '/static/stats.js']:
            with self.subTest(page=page):
                with self.client.get(page) as response:
                    self.assertEqual(response.status_code, 200)

    def test_upload_and_empty(self):
        self.assertEqual(self.client.post('/api/analyze').status_code, 400)
        r = self.client.post('/api/analyze', data={'files': [(io.BytesIO(b'# c\nx=1\n'), 'a.py'), (io.BytesIO(b'// c\nlet x=1;'), 'b.js')]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json['totals']['files'], r.json['totals']['code'], r.json['totals']['comment']), (2, 2, 2))

    def test_upload_above_previous_24mb_limit(self):
        data = b'# header\n' + b' ' * (25 * 1024 * 1024) + b'\nx=1\n'
        r = self.client.post('/api/analyze', data={'files': (io.BytesIO(data), 'large.py')})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([r.json['totals'][k] for k in ('files', 'total', 'code', 'comment', 'blank')], [1, 3, 1, 1, 1])

    def test_upload_page_limit(self):
        response = self.client.get('/code-stats')
        self.assertIn(b'data-upload-limit="1073741824"', response.data)
        self.assertIn('总上传 ≤ 1 GB'.encode(), response.data)
        self.assertNotIn('总上传 ≤ 24 MB'.encode(), response.data)

    def test_request_limit(self):
        previous = app.config['MAX_CONTENT_LENGTH']
        app.config['MAX_CONTENT_LENGTH'] = 100
        try:
            r = self.client.post('/api/analyze', data={'files': (io.BytesIO(b'x' * 101), 'big.py')})
            self.assertEqual(r.status_code, 413)
            self.assertIn('error', r.json)
        finally:
            app.config['MAX_CONTENT_LENGTH'] = previous

    def test_arithmetic_full_score_and_duplicate(self):
        self.client.get('/arithmetic')
        with self.client.session_transaction() as session:
            data = {f'answer_{i}': str(q['answer']) for i, q in enumerate(session['exam_data'])}
        r = self.client.post('/arithmetic/submit', data=data)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'100', r.data)
        self.assertEqual(self.history_count(), 1)
        self.assertEqual(self.client.post('/arithmetic/submit', data=data).status_code, 302)
        self.assertEqual(self.history_count(), 1)

    def seed_game(self):
        with self.client.session_transaction() as session:
            session['game24_nums'] = [3, 3, 5, 1]
            session['game24_finished'] = False

    def test_game_correct_duplicate_and_solution(self):
        self.seed_game()
        for _ in range(2):
            r = self.client.post('/game24/check', data={'expression': '(3+3)*(5-1)'})
            self.assertEqual(r.status_code, 200)
            self.assertIn('答案正确'.encode(), r.data)
        self.assertEqual(self.history_count(), 1)
        self.seed_game()
        self.client.get('/game24/solution')
        self.client.post('/game24/check', data={'expression': '(3+3)*(5-1)'})
        self.assertEqual(self.history_count(), 1)

    def test_game_wrong_expression(self):
        self.seed_game()
        for expression in ['3+3+5+1', '3**3+5+1', '3//3+5+1', '24', '__import__("os")']:
            self.client.post('/game24/check', data={'expression': expression})
        self.assertEqual(self.history_count(), 0)


class SafeExpressions(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(evaluate('(3+3)*(5-1)'), 24)
        self.assertEqual(evaluate('10-3*2'), 4)
        self.assertEqual(evaluate('8/2'), 4)

    def test_rejected_expressions(self):
        for expression in ['2**100', '8//2', '__import__("os")', 'True+2', '4.5*2', '1/0']:
            with self.subTest(expression=expression), self.assertRaises((ValueError, ZeroDivisionError)):
                evaluate(expression)


if __name__ == '__main__':
    unittest.main()
