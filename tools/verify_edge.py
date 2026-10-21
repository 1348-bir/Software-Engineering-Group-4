"""Optional Edge browser QA using DevTools; no additional dependencies needed."""
import base64
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'previews'
OUTPUT.mkdir(exist_ok=True)
EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
BASE = os.environ.get('STUDIO_URL', 'http://127.0.0.1:5050')
PORT = 9226


class DevTools:
    def __init__(self, url):
        parts = urlparse(url)
        self.socket = socket.create_connection((parts.hostname, parts.port), timeout=20)
        key = base64.b64encode(os.urandom(16)).decode()
        header = (f'GET {parts.path} HTTP/1.1\r\nHost: {parts.netloc}\r\nUpgrade: websocket\r\n'
                  f'Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n')
        self.socket.sendall(header.encode())
        response = b''
        while not response.endswith(b'\r\n\r\n'):
            response += self.socket.recv(1)
        assert response.startswith(b'HTTP/1.1 101 '), response
        self.sequence = 0
        self.errors = []

    def read(self, length):
        result = b''
        while len(result) < length:
            part = self.socket.recv(length - len(result))
            if not part:
                raise RuntimeError('Browser connection closed')
            result += part
        return result

    def send(self, payload, opcode=1):
        size = len(payload)
        header = bytes([0x80 | opcode])
        if size < 126:
            header += bytes([0x80 | size])
        elif size < 65536:
            header += bytes([0x80 | 126]) + struct.pack('!H', size)
        else:
            header += bytes([0x80 | 127]) + struct.pack('!Q', size)
        mask = os.urandom(4)
        self.socket.sendall(header + mask + bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload)))

    def receive(self):
        fragments = b''
        while True:
            first, second = self.read(2)
            size = second & 0x7f
            if size == 126:
                size = struct.unpack('!H', self.read(2))[0]
            elif size == 127:
                size = struct.unpack('!Q', self.read(8))[0]
            mask = self.read(4) if second & 0x80 else None
            payload = self.read(size)
            if mask:
                payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
            opcode = first & 0xf
            if opcode == 9:
                self.send(payload, 10)
                continue
            if opcode == 8:
                raise RuntimeError('Browser closed websocket')
            if opcode == 10:
                continue
            fragments += payload
            if first & 0x80:
                return json.loads(fragments)

    def call(self, method, params=None):
        self.sequence += 1
        self.send(json.dumps({'id': self.sequence, 'method': method, 'params': params or {}}).encode())
        while True:
            response = self.receive()
            if response.get('method') == 'Runtime.exceptionThrown':
                self.errors.append(response['params'])
            if response.get('id') == self.sequence:
                if 'error' in response:
                    raise RuntimeError(response['error'])
                return response.get('result', {})

    def js(self, expression):
        response = self.call('Runtime.evaluate', {'expression': expression, 'awaitPromise': True, 'returnByValue': True})
        if 'exceptionDetails' in response:
            raise RuntimeError(response['exceptionDetails'])
        return response['result'].get('value')

    def wait(self, condition):
        expression = '''new Promise((resolve, reject) => {
          const start = Date.now(); const interval = setInterval(() => {
            if (CONDITION) { clearInterval(interval); resolve(true); }
            else if (Date.now() - start > 15000) { clearInterval(interval); reject(new Error('UI timeout')); }
          }, 80);
        })'''.replace('CONDITION', condition)
        for attempt in range(4):
            try:
                return self.js(expression)
            except RuntimeError as exc:
                if attempt == 3 or not any(message in str(exc) for message in ('Inspected target navigated', 'Execution context was destroyed', 'Cannot find context')):
                    raise
                time.sleep(.1)

    def goto(self, path):
        self.call('Page.navigate', {'url': BASE + path})
        self.wait(f'location.pathname === {json.dumps(path)} && document.readyState === "complete"')

    def screenshot(self, name, selector=None):
        self.js('Promise.all(document.getAnimations().filter(a => a.effect && a.effect.getTiming().iterations !== Infinity).map(a => a.finished.catch(() => {})))')
        size = self.call('Page.getLayoutMetrics')['cssContentSize']
        clip = {'x': 0, 'y': 0, 'width': size['width'], 'height': size['height'], 'scale': 1}
        if selector:
            rect = self.js(f'(() => {{ const r = document.querySelector({json.dumps(selector)}).getBoundingClientRect(); return {{x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height}}; }})()')
            clip = {**rect, 'scale': 1}
        result = self.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True, 'clip': clip})
        (OUTPUT / name).write_bytes(base64.b64decode(result['data']))


with tempfile.TemporaryDirectory(prefix='personal-studio-browser-') as temporary:
    temp_path = Path(temporary).resolve()
    assert temp_path.parent == Path(tempfile.gettempdir()).resolve()
    process = subprocess.Popen([EDGE, '--headless', '--disable-gpu', '--no-first-run',
        f'--remote-debugging-port={PORT}', f'--user-data-dir={temp_path / "profile"}', 'about:blank'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    dev = None
    try:
        for _ in range(80):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/list', timeout=1) as response:
                    targets = json.load(response)
                target = next(x for x in targets if x['type'] == 'page')
                break
            except (OSError, StopIteration):
                time.sleep(.2)
        else:
            raise RuntimeError('Edge did not start')
        dev = DevTools(target['webSocketDebuggerUrl'])
        dev.call('Page.enable')
        dev.call('Runtime.enable')
        dev.call('Emulation.setDeviceMetricsOverride', {'width': 1440, 'height': 1050, 'deviceScaleFactor': 1, 'mobile': False})
        dev.goto('/')
        assert dev.js('document.querySelector(".personal-tagline") === null')
        assert dev.js('document.getElementById("members").textContent.includes("徐敬轩") && document.getElementById("members").textContent.includes("文敬雄")')
        assert dev.js('document.querySelectorAll("#members .member-card").length') == 2
        assert dev.js('document.querySelector(".identity-card").getBoundingClientRect().height > 300')
        assert dev.js('Array.from(document.querySelectorAll("#tools a"), a => a.getAttribute("href")).includes("/code-stats")')
        assert dev.js('Array.from(document.querySelectorAll("#tools a"), a => a.getAttribute("href")).includes("/math")')
        dev.screenshot('home-desktop.png')
        dev.goto('/code-stats')
        dev.js('document.getElementById("function-demo").click()')
        dev.wait('document.getElementById("message").textContent.includes("统计完成：5 个文件")')
        assert dev.js('document.querySelectorAll("#language-summary-rows tr").length') == 5
        assert dev.js('Array.from(document.querySelectorAll("#language-summary-rows tr"), tr=>tr.children[5].textContent)') == ['1','1','1','2','1']
        assert dev.js('document.querySelectorAll("#language-summary-rows tr")[3].children[9].textContent') == '2'
        dev.screenshot('function-statistics-desktop.png')
        dev.screenshot('function-summary.png', '.language-summary-panel')
        dev.goto('/code-stats')
        if os.environ.get('SKIP_REMOTE_QA') != '1':
            dev.js('document.getElementById("source-url").value="https://github.com/pallets/flask/blob/main/examples/tutorial/flaskr/__init__.py"; document.getElementById("url-form").requestSubmit()')
            dev.wait('document.getElementById("url-message").textContent.includes("统计完成：1 个文件")')
            assert '__init__.py' in dev.js('document.getElementById("file-rows").textContent')
            dev.screenshot('url-stats-desktop.png')
        dev.js('document.getElementById("source-url").value="http://127.0.0.1/a.py"; document.getElementById("url-form").requestSubmit()')
        dev.wait('document.getElementById("url-message").textContent.includes("内网地址")')
        assert not dev.js('document.getElementById("analyze-url").disabled')
        assert dev.js('document.getElementById("results").hidden')
        dev.goto('/code-stats')
        assert dev.js('Number(document.getElementById("drop-zone").dataset.uploadLimit)') == 1024 ** 3
        dev.js('updateSelection([{name:"large.py",size:1073741825}])')
        assert dev.js('document.getElementById("analyze").disabled')
        assert '单文件超过 1 GB' in dev.js('document.getElementById("message").textContent')
        dev.js('updateSelection([{name:"a.py",size:1073741824}])')
        assert not dev.js('document.getElementById("analyze").disabled')
        dev.js('updateSelection([{name:"a.py",size:600000000},{name:"b.py",size:600000000}])')
        assert dev.js('document.getElementById("analyze").disabled')
        assert '文件总大小超过 1 GB' in dev.js('document.getElementById("message").textContent')
        dev.js('document.getElementById("demo").click()')
        dev.wait('document.getElementById("message").textContent.includes("统计完成：3 个文件，6 行含有注释。")')
        assert dev.js('Array.from(document.querySelectorAll("#metrics .metric strong"), x=>x.textContent)') == ['3', '13', '7', '5', '1']
        assert dev.js('document.querySelectorAll("#file-rows tr").length') == 3
        dev.screenshot('stats-desktop.png')
        dev.js('const field=document.getElementById("filter");field.value="python";field.dispatchEvent(new Event("input"))')
        assert dev.js('document.querySelectorAll("#file-rows tr").length') == 1
        assert 'hello.py' in dev.js('document.getElementById("file-rows").textContent')
        dev.js('window.exportedBlob=null; window.exportedName=null; URL.createObjectURL=blob=>{window.exportedBlob=blob; return "blob:qa"};HTMLAnchorElement.prototype.click=function(){window.exportedName=this.download};document.getElementById("export").click()')
        assert '"合计","","13","7","5","1","6"' in dev.js('window.exportedBlob.text()')
        assert dev.js('window.exportedName') == '代码统计.csv'
        dev.js('document.getElementById("clear").click()')
        assert dev.js('document.getElementById("results").hidden && document.getElementById("analyze").disabled')
        fixture = temp_path / 'test.py'
        fixture.write_bytes(b'# comment\nvalue = "# string" # tail\n')
        dom = dev.call('DOM.getDocument')['root']['nodeId']
        node = dev.call('DOM.querySelector', {'nodeId': dom, 'selector': '#file-input'})['nodeId']
        dev.call('DOM.setFileInputFiles', {'nodeId': node, 'files': [str(fixture)]})
        dev.js('document.getElementById("analyze").click()')
        dev.wait('document.getElementById("message").textContent.includes("统计完成：1 个文件，2 行含有注释。")')
        assert dev.js('Array.from(document.querySelectorAll("#metrics .metric strong"), x=>x.textContent)') == ['1', '2', '1', '1', '0']
        fixture_zip = temp_path / 'project.zip'
        with zipfile.ZipFile(fixture_zip, 'w') as z:
            z.writestr('src/a.js', '// comment\nconst value=1;')
            z.writestr('unknown.xyzunknown', 'text')
        dev.call('DOM.setFileInputFiles', {'nodeId': node, 'files': [str(fixture_zip)]})
        dev.js('document.getElementById("analyze").click()')
        dev.wait('document.getElementById("message").textContent.includes("统计完成：1 个文件，1 行含有注释。")')
        assert not dev.js('document.getElementById("skipped-panel").hidden')
        assert '未识别的语言' in dev.js('document.getElementById("skipped-list").textContent')
        folder = temp_path / 'folder-example'
        (folder / 'src').mkdir(parents=True)
        (folder / 'src' / 'main.py').write_text('# folder\nx=1\n', encoding='utf-8')
        folder_node = dev.call('DOM.querySelector', {'nodeId': dom, 'selector': '#folder-input'})['nodeId']
        dev.call('DOM.setFileInputFiles', {'nodeId': folder_node, 'files': [str(folder)]})
        dev.wait('document.getElementById("selected-label").textContent.includes("已选择 1 个文件")')
        dev.js('document.getElementById("analyze").click()')
        dev.wait('document.getElementById("message").textContent.includes("统计完成：1 个文件，1 行含有注释。")')
        assert 'folder-example/src/main.py' in dev.js('document.getElementById("file-rows").textContent')
        dev.goto('/math')
        dev.screenshot('math-desktop.png')
        dev.goto('/arithmetic')
        assert dev.js('document.querySelectorAll("input[type=number]").length') == 10
        dev.goto('/game24')
        assert dev.js('document.querySelectorAll(".num-card").length') == 4
        dev.js('document.getElementById("expression").value="24";document.getElementById("gameForm").requestSubmit()')
        dev.wait('document.querySelector(".message")?.textContent.includes("必须且只能")')
        dev.goto('/game24/solution')
        assert '参考答案' in dev.js('document.querySelector(".message").textContent')
        for width in [390, 360]:
            dev.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 844, 'deviceScaleFactor': 1, 'mobile': False})
            for path in ['/', '/members', '/members/xu-jingxuan', '/members/wen-jingxiong', '/projects', '/code-stats', '/math', '/math/', '/math/print', '/math/upload', '/arithmetic', '/game24', '/game24/', '/dice/', '/history', '/math/history', '/game24/history', '/dice/history']:
                dev.goto(path)
                assert dev.js('document.documentElement.scrollWidth <= window.innerWidth'), f'Overflow: {width} {path}'
                if width == 390 and path == '/':
                    dev.screenshot('home-mobile.png')
                elif width == 390 and path == '/code-stats':
                    dev.js('document.getElementById("demo").click()')
                    dev.wait('document.getElementById("message").textContent.includes("统计完成：3 个文件，6 行含有注释。")')
                    assert dev.js('document.documentElement.scrollWidth <= window.innerWidth')
                    dev.screenshot('stats-mobile.png')
        assert not dev.errors, dev.errors
        print(json.dumps({'status': 'passed', 'screenshots': str(OUTPUT), 'javascript_errors': dev.errors}, ensure_ascii=False))
    finally:
        if dev:
            try:
                dev.call('Browser.close')
            except (OSError, RuntimeError):
                pass
            dev.socket.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=10)
