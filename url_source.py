"""Fetch public source URLs into a temporary file and reuse the upload analyzer."""
import http.client
import ipaddress
import re
import socket
import tempfile
import time
from email.message import Message
from pathlib import PurePosixPath
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

from werkzeug.datastructures import FileStorage
from code_stats import MAX_UPLOAD, READ_CHUNK, analyze_uploads

MAX_REDIRECTS = 5
DOWNLOAD_SECONDS = 600
SOCKET_TIMEOUT = 20


def normalize_url(value):
    if not isinstance(value, str):
        raise ValueError('请输入有效的网址')
    value = value.strip()
    if not value or len(value) > 4096 or re.search(r'[\x00-\x20\x7f]', value):
        raise ValueError('请输入完整的 HTTP 或 HTTPS 网址，不要包含空格')
    try:
        parts = urlsplit(value)
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            raise ValueError('只支持 HTTP 和 HTTPS 网址')
        if parts.username is not None or parts.password is not None:
            raise ValueError('请使用无需登录、且不含账号密码的公开链接')
        port = parts.port
        if port not in (None, 80, 443):
            raise ValueError('网址只支持标准的 80 或 443 端口')
        host = parts.hostname.encode('idna').decode('ascii').lower()
    except (UnicodeError, ValueError) as exc:
        raise ValueError(str(exc) or '网址格式无效') from exc
    netloc = f'[{host}]' if ':' in host else host
    if port:
        netloc += f':{port}'
    path = quote(parts.path or '/', safe="/%:@!$&'()*+,;=-._~")
    query = quote(parts.query, safe="%=&?/:@!$'()*+,;~-._")
    normalized = urlunsplit((parts.scheme, netloc, path, query, ''))
    if host in ('github.com', 'www.github.com'):
        segments = path.strip('/').split('/')
        if len(segments) == 2 and all(segments):
            owner, repo = segments
            repo = repo.removesuffix('.git')
            return f'https://codeload.github.com/{owner}/{repo}/zip/HEAD'
        if len(segments) >= 5 and segments[2] == 'blob':
            raw_path = '/'.join(segments[:2] + segments[3:])
            return f'https://raw.githubusercontent.com/{raw_path}'
        if len(segments) >= 3 and segments[2] == 'tree':
            raise ValueError('暂不支持 GitHub 子目录网址，请粘贴仓库首页或 ZIP 下载链接')
    return normalized


def open_public_url(url):
    """Resolve and pin a public address, preserving HTTPS certificate/hostname checks."""
    parts = urlsplit(url)
    host, port = parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80)
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError('请使用公开互联网网址，不支持本机或内网地址')
    # Prefer IPv4 for machines without IPv6 connectivity. Never resolve again on connect.
    addresses.sort(key=lambda row: row[0] != socket.AF_INET)
    address = addresses[0][4][0]
    cls = http.client.HTTPSConnection if parts.scheme == 'https' else http.client.HTTPConnection
    connection = cls(host, port=port, timeout=SOCKET_TIMEOUT)
    connection._create_connection = lambda target, timeout, source_address: socket.create_connection(
        (address, port), timeout=timeout, source_address=source_address)
    try:
        path = parts.path or '/'
        if parts.query:
            path += '?' + parts.query
        connection.request('GET', path, headers={
            'User-Agent': 'PersonalCodeStudio/1.0', 'Accept-Encoding': 'identity',
            'Accept': '*/*', 'Connection': 'close',
        })
        return connection, connection.getresponse()
    except Exception:
        connection.close()
        raise


def source_filename(url, response):
    headers = Message()
    headers['Content-Disposition'] = response.getheader('Content-Disposition', '')
    candidate = headers.get_filename()
    if not candidate:
        candidate = unquote(PurePosixPath(urlsplit(url).path).name) or 'index'
    candidate = candidate.replace('\\', '/').rsplit('/', 1)[-1]
    candidate = re.sub(r'[\x00-\x1f\x7f]', '', candidate)[:200] or 'source'
    content_type = response.getheader('Content-Type', '').split(';')[0].strip().lower()
    if content_type in ('application/zip', 'application/x-zip-compressed') and not candidate.lower().endswith('.zip'):
        candidate += '.zip'
    elif content_type in ('text/html', 'application/xhtml+xml'):
        candidate = PurePosixPath(candidate).stem + '.html'
    return candidate


def analyze_url(value):
    url = normalize_url(value)
    start = time.monotonic()
    try:
        for redirect in range(MAX_REDIRECTS + 1):
            connection, response = open_public_url(url)
            try:
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader('Location')
                    if not location or redirect == MAX_REDIRECTS:
                        raise ValueError('网址重定向过多或缺少目标地址，请使用文件直链')
                    url = normalize_url(urljoin(url, location))
                    continue
                if response.status != 200:
                    raise ValueError(f'下载失败（HTTP {response.status}），请确认链接公开可访问且无需登录')
                if response.getheader('Content-Encoding', 'identity').lower() not in ('identity', ''):
                    raise ValueError('该网址返回压缩网页，请改用源码文件或 ZIP 下载直链')
                length = response.getheader('Content-Length')
                expected = None
                if length is not None:
                    try:
                        expected = int(length)
                    except ValueError as exc:
                        raise ValueError('远程服务器返回了无效的文件大小') from exc
                    if expected < 0:
                        raise ValueError('远程服务器返回了无效的文件大小')
                    if expected > MAX_UPLOAD:
                        raise ValueError('网址文件超过 1 GB，请选择更小的文件或仓库')
                filename = source_filename(url, response)
                with tempfile.TemporaryFile() as file:
                    size = 0
                    while True:
                        if time.monotonic() - start > DOWNLOAD_SECONDS:
                            raise ValueError('下载耗时过长，请下载到本地后使用文件上传')
                        chunk = response.read1(min(READ_CHUNK, MAX_UPLOAD - size + 1))
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > MAX_UPLOAD:
                            raise ValueError('网址文件超过 1 GB，请选择更小的文件或仓库')
                        file.write(chunk)
                    if expected is not None and size != expected:
                        raise ValueError('文件下载不完整，请重试或使用本地上传')
                    file.seek(0)
                    return analyze_uploads([FileStorage(stream=file, filename=filename)])
            finally:
                response.close()
                connection.close()
    except ValueError:
        raise
    except (OSError, http.client.HTTPException) as exc:
        raise ValueError('无法下载该网址，请检查网络连接、网址及证书，或下载后使用本地上传') from exc
