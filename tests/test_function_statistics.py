import io
import unittest
from werkzeug.datastructures import FileStorage
from app import app
from code_stats import analyze_uploads, count_source


def file(name, source):
    return FileStorage(stream=io.BytesIO(source.encode()), filename=name)


class FunctionStatistics(unittest.TestCase):
    def test_c_definitions_not_prototypes_or_calls(self):
        source = '''int declared(int a);
int add(int a, int b) {
  // comment
  return a + b; // inline
}
int main(void)
{
  /* comment */
  return add(1, 2);
}
'''
        row = count_source('main.c', source.encode())
        self.assertEqual(row['_function_lengths'], [3, 4])
        self.assertEqual([row[k] for k in ('functions', 'function_max', 'function_min', 'function_mean', 'function_median')], [2, 4, 3, 3.5, 3.5])

    def test_cpp_constructor_method_and_free_function(self):
        source = '''struct Demo {
  Demo() {}
  int get() const { return 1; }
  void declaration();
};
int main() {
  Demo d;
  return d.get();
}
'''
        row = count_source('main.cpp', source.encode())
        self.assertEqual((row['language'], row['functions']), ('C++', 3))
        self.assertEqual(row['_function_lengths'], [1, 1, 4])

    def test_java_methods_constructors_and_abstract_declarations(self):
        source = '''abstract class Demo {
  Demo() {}
  int f() {
    // comment
    return 1;
  }
  abstract int missing();
}
'''
        row = count_source('Demo.java', source.encode())
        self.assertEqual(row['_function_lengths'], [1, 3])
        self.assertEqual((row['functions'], row['function_mean']), (2, 2))

    def test_csharp_expression_body_and_constructor(self):
        source = '''abstract class Demo {
  public Demo() {}
  public int F()
  {
    // comment
    return 1;
  }
  public int G() => F();
  public abstract int Missing();
}
'''
        row = count_source('Demo.cs', source.encode())
        self.assertEqual((row['language'], row['functions']), ('C#', 3))
        self.assertEqual(row['_function_lengths'], [1, 4, 1])

    def test_python_decorator_nested_and_async(self):
        source = '''@decorate
def outer():
    # comment
    def inner():
        return 1

    return inner()

async def task():
    return 2
'''
        row = count_source('demo.py', source.encode())
        self.assertEqual(sorted(row['_function_lengths']), [2, 2, 5])
        self.assertEqual([row[k] for k in ('functions', 'function_max', 'function_min', 'function_mean', 'function_median')], [3, 5, 2, 3, 2])

    def test_comments_and_strings_do_not_create_functions(self):
        source = '''// int fake() { return 1; }
const char *s = "int fake2() { return 2; }";
/* int fake3() { return 3; } */
int real() { return 1; }
'''
        self.assertEqual(count_source('a.c', source.encode())['functions'], 1)

    def test_multiline_pure_comment_excluded(self):
        source = 'def run():\n    # c\n\n    x = "# literal" # inline\n    return x\n'
        self.assertEqual(count_source('a.py', source.encode())['_function_lengths'], [3])

    def test_no_functions_and_invalid_python(self):
        plain = count_source('a.py', b'x = 1\n')
        self.assertEqual(plain['functions'], 0)
        self.assertIsNone(plain['function_min'])
        broken = count_source('broken.py', b'def broken(:\n')
        self.assertIsNone(broken['functions'])
        self.assertTrue(broken['function_warning'])

    def test_language_aggregation_uses_all_functions(self):
        report = analyze_uploads([
            file('a.py', 'def a():\n    return 1\n'),
            file('b.py', 'def b():\n    x = 1\n    y = 2\n    return x + y\ndef c(): return 3\n'),
        ])
        row = next(row for row in report['language_summary'] if row['language'] == 'Python')
        self.assertEqual([row[k] for k in ('files', 'functions', 'function_max', 'function_min', 'function_mean', 'function_median')], [2, 3, 4, 1, 2.33, 2])
        self.assertEqual([r['language'] for r in report['language_summary']], ['C', 'C++', 'Java', 'Python', 'C#'])
        self.assertEqual(len(report['languages']), 1)
        self.assertNotIn('_function_lengths', report['files'][0])

    def test_unsupported_language_retains_basic_statistics(self):
        report = analyze_uploads([file('style.css', '/* c */\na { color: red; }\n')])
        row = report['language_summary'][-1]
        self.assertEqual((row['language'], row['files'], row['comment']), ('CSS', 1, 1))
        self.assertFalse(row['function_supported'])
        self.assertIsNone(row['functions'])

    def test_upload_api_has_requested_columns(self):
        response = app.test_client().post('/api/analyze', data={'files': (io.BytesIO(b'def f():\n    return 1\n'), 'a.py')})
        self.assertEqual(response.status_code, 200)
        row = next(r for r in response.json['language_summary'] if r['language'] == 'Python')
        self.assertEqual((row['functions'], row['function_max'], row['function_median']), (1, 2, 2))
        html = app.test_client().get('/code-stats').get_data(as_text=True)
        for title in ('源文件数', '代码行数', '空行数', '注释行数', '函数个数', '最大值', '最小值', '均值', '中位数'):
            self.assertIn(title, html)


if __name__ == '__main__':
    unittest.main()
