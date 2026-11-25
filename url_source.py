"""网址导入：把公开源码链接下载到临时文件，再复用上传统计引擎。

安全约束（防止被当成内网探测工具）：
1. 只允许 http/https、标准端口，禁止带账号密码的链接；
2. 域名解析后要求全部是公网 IP，并把连接固定到已校验的 IP，避免 DNS 重绑定；
3. 逐跳校验重定向，每一跳都重新走上面的检查；
4. 下载有总时长与 1 GB 大小上限，内容写入临时文件后关闭。
"""
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

MAX_REDIRECTS = 5          # 最多跟 5 次重定向
DOWNLOAD_SECONDS = 600     # 单次下载总时长上限（秒）
SOCKET_TIMEOUT = 20        # 单次 socket 读超时（秒）


def normalize_url(value):
    """校验并规范化网址，返回真正要下载的地址。

    除了基础校验，还会把 GitHub 的「仓库首页 / blob 文件页」转换成
    codeload 的 ZIP 地址或 raw 直链；GitHub 子目录页直接拒绝。
    """
    if not isinstance(value, str):
        raise ValueError('请输入有效的网址')
    value = value.strip()
    # 长度上限与控制字符检查：防止把奇怪的内容塞进 HTTP 请求行。
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
        # 域名转 IDNA（中文域名等）并统一小写。
        host = parts.hostname.encode('idna').decode('ascii').lower()
    except (UnicodeError, ValueError) as exc:
        raise ValueError(str(exc) or '网址格式无效') from exc
    netloc = f'[{host}]' if ':' in host else host     # IPv6 地址需要方括号
    if port:
        netloc += f':{port}'
    # 只编码路径与查询串，保留合法保留字符；丢掉 URL 中的 #fragment。
    path = quote(parts.path or '/', safe="/%:@!$&'()*+,;=-._~")
    query = quote(parts.query, safe="%=&?/:@!$'()*+,;~-._")
    normalized = urlunsplit((parts.scheme, netloc, path, query, ''))
    if host in ('github.com', 'www.github.com'):
        segments = path.strip('/').split('/')
        if len(segments) == 2 and all(segments):
            # 仓库首页 → 直接下 ZIP
            owner, repo = segments
            repo = repo.removesuffix('.git')
            return f'https://codeload.github.com/{owner}/{repo}/zip/HEAD'
        if len(segments) >= 5 and segments[2] == 'blob':
            # 单文件页 → 转成 raw 直链
            raw_path = '/'.join(segments[:2] + segments[3:])
            return f'https://raw.githubusercontent.com/{raw_path}'
        if len(segments) >= 3 and segments[2] == 'tree':
            raise ValueError('暂不支持 GitHub 子目录网址，请粘贴仓库首页或 ZIP 下载链接')
    return normalized


def open_public_url(url):
    """建立到公网地址的连接，返回 ``(连接, 响应)``。

    先解析域名并确认所有地址都是公网 IP，然后把这些 IP 中的第一个
    固定给 socket 使用——连接阶段不再二次解析，从而避免 DNS 重绑定攻击；
    HTTPS 仍然用原域名做 SNI 与证书校验。
    """
    parts = urlsplit(url)
    host, port = parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80)
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError('请使用公开互联网网址，不支持本机或内网地址')
    # 优先 IPv4（部分机器没有 IPv6 出口）；连接时只使用这一条已校验的地址。
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
            'User-Agent': 'PersonalCodeStudio/1.0',
            'Accept-Encoding': 'identity',   # 要求不压缩，方便按字节计数
            'Accept': '*/*', 'Connection': 'close',
        })
        return connection, connection.getresponse()
    except Exception:
        connection.close()
        raise


def source_filename(url, response):
    """从响应头或 URL 推断文件名，并按内容类型补充扩展名。"""
    headers = Message()
    headers['Content-Disposition'] = response.getheader('Content-Disposition', '')
    candidate = headers.get_filename()
    if not candidate:
        candidate = unquote(PurePosixPath(urlsplit(url).path).name) or 'index'
    # 去掉路径分隔符与控制字符，并限制长度，避免写文件时出问题。
    candidate = candidate.replace('\\', '/').rsplit('/', 1)[-1]
    candidate = re.sub(r'[\x00-\x1f\x7f]', '', candidate)[:200] or 'source'
    content_type = response.getheader('Content-Type', '').split(';')[0].strip().lower()
    if content_type in ('application/zip', 'application/x-zip-compressed') and not candidate.lower().endswith('.zip'):
        candidate += '.zip'
    elif content_type in ('text/html', 'application/xhtml+xml'):
        # 普通网页只能拿到 HTML 本身（后端代码拿不到），统一标记为 .html
        candidate = PurePosixPath(candidate).stem + '.html'
    return candidate


def analyze_url(value):
    """下载网址内容并统计，返回与上传接口一致的报告结构。"""
    url = normalize_url(value)
    start = time.monotonic()
    try:
        # 手动处理重定向：每一跳都重新校验，避免被引到内网。
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
                # Content-Length 只作为参考：既能提前拒绝超大文件，也能在结束时校验完整性。
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
                # 临时文件在 with 结束时自动删除，处理完不占用磁盘。
                with tempfile.TemporaryFile() as file:
                    size = 0
                    while True:
                        if time.monotonic() - start > DOWNLOAD_SECONDS:
                            raise ValueError('下载耗时过长，请下载到本地后使用文件上传')
                        # 多读 1 字节用于判断是否超限。
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
                    # 包成 FileStorage 后复用上传统计流程，保证两种入口结果一致。
                    return analyze_uploads([FileStorage(stream=file, filename=filename)])
            finally:
                response.close()
                connection.close()
    except ValueError:
        raise
    except (OSError, http.client.HTTPException) as exc:
        # 网络层异常统一转成用户能看懂的提示。
        raise ValueError('无法下载该网址，请检查网络连接、网址及证书，或下载后使用本地上传') from exc
