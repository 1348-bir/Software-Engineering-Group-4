import io
import unittest
import zipfile
from werkzeug.datastructures import FileStorage
from app import app
from code_stats import analyze_uploads, count_source, MAX_FILES, MAX_UPLOAD_FORM_PARTS


class StatsAudit(unittest.TestCase):
    def test_form_limit_matches_advertised_file_limit(self):
        self.assertEqual(app.config['MAX_FORM_PARTS'], MAX_UPLOAD_FORM_PARTS)
        self.assertGreater(app.config['MAX_FORM_PARTS'], MAX_FILES)

    def test_real_upload_more_than_previous_1200_parts(self):
        files=[(io.BytesIO(b'# note\nx=1\n'), f'file{i}.py') for i in range(1201)]
        response=app.test_client().post('/api/analyze',data={'files':files})
        self.assertEqual(response.status_code,200,response.get_data(as_text=True)[:100])
        self.assertEqual(response.json['totals']['files'],1201)
        self.assertEqual(response.json['totals']['code'],1201)
        self.assertEqual(response.json['totals']['comment'],1201)

    def test_zip_absolute_and_parent_paths_not_counted(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            for name in ('/outside.py','C:/outside.py','C:\\outside.py','../outside.py'):
                archive.writestr(name,'x=1\n')
            archive.writestr('src/good.py','# note\nx=1\n')
        report=analyze_uploads([FileStorage(stream=io.BytesIO(stream.getvalue()),filename='source.zip')])
        self.assertEqual((report['totals']['files'],report['totals']['skipped']),(1,4))
        self.assertEqual((report['totals']['total'],report['totals']['code'],report['totals']['comment']),(2,1,1))

    def test_direct_windows_absolute_path_is_skipped(self):
        report=analyze_uploads([FileStorage(stream=io.BytesIO(b'x=1\n'),filename='C:/outside.py')])
        self.assertEqual((report['totals']['files'],report['totals']['skipped']),(0,1))

    def test_physical_lines_and_comment_markers_in_strings(self):
        samples={
            'a.py':('# heading\nx = "# value" # inline\n\ndef f():\n    return x\n',(5,3,1,1,2)),
            'a.cpp':('// heading\nint f() {\n // comment\n return 1; /* inline */\n}\n',(5,3,2,0,3)),
            'Demo.java':('class Demo {\n // note\n int f() { return 1; }\n}\n',(4,3,1,0,1)),
            'Demo.cs':('class Demo {\n // note\n int F() => 1;\n}\n',(4,3,1,0,1)),
            'a.js':('// note\nconst s="https://x"; // inline\n\n',(3,1,1,1,2)),
            'a.sql':('-- note\nSELECT \'-- text\';\n',(2,1,1,0,1)),
        }
        for name,(source,expected) in samples.items():
            with self.subTest(name=name):
                row=count_source(name,source.encode())
                self.assertEqual(tuple(row[k] for k in ('total','code','comment','blank','comment_any')),expected)
                self.assertEqual(row['total'],row['code']+row['comment']+row['blank'])

    def test_crlf_and_cr_match_lf_for_function_lengths(self):
        source='def f():\n    # note\n\n    return 1\n'
        for nl in ('\n','\r\n','\r'):
            with self.subTest(nl=repr(nl)):
                row=count_source('a.py',source.replace('\n',nl).encode())
                self.assertEqual(row['_function_lengths'],[2])
                self.assertEqual((row['total'],row['blank']),(4,1))
