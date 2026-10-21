import io
import socket
import unittest
import zipfile
from unittest.mock import Mock, patch

from app import app
from url_source import analyze_url, normalize_url, open_public_url


class Response(io.BytesIO):
    def __init__(self, body=b'', status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}

    def getheader(self, name, default=None):
        return self.headers.get(name, default)


def opened(body=b'', status=200, headers=None):
    return Mock(), Response(body, status, headers)


class RemoteSourceTests(unittest.TestCase):
    def test_normalize_github(self):
        self.assertEqual(normalize_url('https://github.com/pallets/flask/'), 'https://codeload.github.com/pallets/flask/zip/HEAD')
        self.assertEqual(normalize_url('https://github.com/pallets/flask.git'), 'https://codeload.github.com/pallets/flask/zip/HEAD')
        self.assertEqual(normalize_url('https://github.com/pallets/flask/blob/main/src/flask/app.py?plain=1#L1'), 'https://raw.githubusercontent.com/pallets/flask/main/src/flask/app.py')
        self.assertEqual(normalize_url(' https://example.com/a.py#L2 '), 'https://example.com/a.py')
        self.assertIn('%E4%B8%AD', normalize_url('https://example.com/中文.py'))

    def test_invalid_urls(self):
        for value in [None, 123, '', 'file:///etc/passwd', 'ftp://example.com/a.py', 'https://u:p@example.com/a.py', 'http://example.com:8080/a.py', 'http://example.com/a\r\nX:1', 'x' * 4097, 'https://github.com/pallets/flask/tree/main/src']:
            with self.subTest(value=str(value)[:60]), self.assertRaises(ValueError):
                normalize_url(value)

    def test_blocks_nonpublic_dns_results(self):
        for ip in ['127.0.0.1', '10.0.0.1', '192.168.1.1', '169.254.169.254', '::1', 'fc00::1', '0.0.0.0', '::ffff:127.0.0.1']:
            addresses = [(socket.AF_INET6 if ':' in ip else socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 80))]
            with self.subTest(ip=ip), patch('url_source.socket.getaddrinfo', return_value=addresses), patch('url_source.http.client.HTTPConnection') as connection:
                with self.assertRaisesRegex(ValueError, '内网'):
                    open_public_url('http://example.com/a.py')
                connection.assert_not_called()

    def test_public_connection_pins_validated_address(self):
        records = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('1.1.1.1', 443))]
        with patch('url_source.socket.getaddrinfo', return_value=records), patch('url_source.http.client.HTTPSConnection') as cls, patch('url_source.socket.create_connection') as connect:
            connection, response = open_public_url('https://example.com/a.py?raw=1')
            connection._create_connection(('example.com', 443), 20, None)
            connect.assert_called_once_with(('1.1.1.1', 443), timeout=20, source_address=None)
            self.assertEqual(connection.request.call_args.args[:2], ('GET', '/a.py?raw=1'))
            cls.assert_called_once_with('example.com', port=443, timeout=20)

    def test_plain_source(self):
        pair = opened(b'# header\nx = "# literal" # note\n')
        with patch('url_source.open_public_url', return_value=pair):
            result = analyze_url('https://example.com/code.py')
        self.assertEqual([result['totals'][k] for k in ('files', 'total', 'code', 'comment', 'comment_any')], [1, 2, 1, 1, 2])
        self.assertTrue(pair[1].closed)
        pair[0].close.assert_called_once()

    def test_zip_download_filename(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('src/a.py', '# c\nx=1\n')
            z.writestr('src/b.js', '// c\nlet x=1;\n')
        with patch('url_source.open_public_url', return_value=opened(archive.getvalue(), headers={'Content-Type': 'application/zip'})):
            result = analyze_url('https://example.com/download')
        self.assertEqual(result['totals']['files'], 2)
        self.assertEqual(result['totals']['comment'], 2)

    def test_content_disposition_and_unicode(self):
        headers = {'Content-Disposition': "attachment; filename*=UTF-8''%E4%B8%AD%E6%96%87.py"}
        with patch('url_source.open_public_url', return_value=opened(b'x=1\n', headers=headers)):
            result = analyze_url('https://example.com/download?id=1')
        self.assertEqual(result['files'][0]['name'], '中文.py')

    def test_website_html(self):
        with patch('url_source.open_public_url', return_value=opened(b'<!-- c -->\n<p>Hello</p>\n', headers={'Content-Type': 'text/html; charset=utf-8'})):
            result = analyze_url('https://example.com/')
        self.assertEqual(result['files'][0]['name'], 'index.html')
        self.assertEqual((result['totals']['code'], result['totals']['comment']), (1, 1))

    def test_redirect(self):
        first, second = opened(status=302, headers={'Location': '/code.py'}), opened(b'x=1')
        with patch('url_source.open_public_url', side_effect=[first, second]) as download:
            self.assertEqual(analyze_url('https://example.com/start')['totals']['files'], 1)
            self.assertEqual(download.call_args_list[1].args[0], 'https://example.com/code.py')
        self.assertTrue(first[1].closed)

    def test_private_redirect_is_validated(self):
        first = opened(status=302, headers={'Location': 'http://127.0.0.1/a.py'})
        with patch('url_source.open_public_url', side_effect=[first, ValueError('请使用公开互联网网址，不支持本机或内网地址')]) as download:
            with self.assertRaisesRegex(ValueError, '内网'):
                analyze_url('https://example.com/start')
            self.assertEqual(download.call_args_list[1].args[0], 'http://127.0.0.1/a.py')

    def test_redirect_limits(self):
        with patch('url_source.open_public_url', side_effect=lambda url: opened(status=302, headers={'Location': '/loop'})):
            with self.assertRaisesRegex(ValueError, '重定向'):
                analyze_url('https://example.com/loop')

    def test_remote_errors(self):
        for status in (401, 403, 404, 500):
            with self.subTest(status=status), patch('url_source.open_public_url', return_value=opened(status=status)):
                with self.assertRaisesRegex(ValueError, str(status)):
                    analyze_url('https://example.com/a.py')

    def test_limit_with_and_without_content_length(self):
        for headers in ({}, {'Content-Length': '9'}):
            with self.subTest(headers=headers), patch('url_source.MAX_UPLOAD', 8), patch('url_source.open_public_url', return_value=opened(b'123456789', headers=headers)):
                with self.assertRaisesRegex(ValueError, '1 GB'):
                    analyze_url('https://example.com/a.py')
        with patch('url_source.MAX_UPLOAD', 8), patch('url_source.open_public_url', return_value=opened(b'#1234567', headers={'Content-Length': '8'})):
            self.assertEqual(analyze_url('https://example.com/a.py')['totals']['files'], 1)

    def test_incomplete_download_and_encoding(self):
        for headers in ({'Content-Length': '9'}, {'Content-Length': 'wrong'}, {'Content-Encoding': 'gzip'}):
            with self.subTest(headers=headers), patch('url_source.open_public_url', return_value=opened(b'x=1', headers=headers)):
                with self.assertRaises(ValueError):
                    analyze_url('https://example.com/a.py')

    def test_network_error(self):
        with patch('url_source.open_public_url', side_effect=socket.timeout()):
            with self.assertRaisesRegex(ValueError, '无法下载'):
                analyze_url('https://example.com/a.py')

    def test_download_deadline(self):
        with patch('url_source.time.monotonic', side_effect=[0, 601]), patch('url_source.open_public_url', return_value=opened(b'x=1')):
            with self.assertRaisesRegex(ValueError, '耗时过长'):
                analyze_url('https://example.com/a.py')

    def test_api_integration_and_invalid_json(self):
        client = app.test_client()
        for data in (None, [], {}, {'url': 'file:///tmp/a.py'}):
            with self.subTest(data=data):
                self.assertEqual(client.post('/api/analyze-url', json=data).status_code, 400)
        with patch('url_source.open_public_url', return_value=opened(b'# c\nx=1\n')):
            response = client.post('/api/analyze-url', json={'url': 'https://example.com/a.py'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['totals']['files'], 1)
        self.assertEqual(response.json['totals']['comment'], 1)


if __name__ == '__main__':
    unittest.main()
