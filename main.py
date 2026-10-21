# main.py
import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for

from math_practice import bp as math_bp
from math_practice.routes import init_question_bank
from game_24 import bp as game24_bp
from dice_game import bp as dice_bp

app = Flask(__name__)
app.secret_key = 'change-this-secret-key'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# ---------------- 头像上传 ----------------

AVATAR_DIR = Path(app.static_folder) / 'uploads'
ALLOWED_AVATAR_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
MAX_AVATAR_BYTES = 3 * 1024 * 1024


def latest_avatar():
    """返回 static/uploads 下最新的头像文件，没有上传过则返回 None。"""
    if not AVATAR_DIR.is_dir():
        return None
    files = [p for p in AVATAR_DIR.iterdir()
             if p.is_file() and p.suffix.lower() in ALLOWED_AVATAR_EXT]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _back_url():
    """回到来源页面；非本站来源则回首页，避免开放重定向。"""
    ref = request.referrer
    if ref and ref.startswith(request.host_url):
        return ref
    return url_for('index')


def _with_param(url, key, value):
    return f'{url}{"&" if "?" in url else "?"}{key}={value}'


@app.context_processor
def inject_avatar():
    """让所有模板都能拿到 avatar_url（未上传时为 None）。"""
    avatar = latest_avatar()
    if avatar is None:
        return {'avatar_url': None}
    rel = url_for('static', filename=f'uploads/{avatar.name}')
    return {'avatar_url': f'{rel}?v={int(avatar.stat().st_mtime)}'}


@app.route('/avatar/upload', methods=['POST'])
def upload_avatar():
    """上传/更换头像，只保留最新的一张。"""
    back = _back_url()
    file = request.files.get('avatar')
    if not file or not file.filename:
        return redirect(back)

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_AVATAR_EXT:
        return redirect(_with_param(back, 'avatar_error', 'format'))

    data = file.read()
    if not data:
        return redirect(back)
    if len(data) > MAX_AVATAR_BYTES:
        return redirect(_with_param(back, 'avatar_error', 'size'))

    try:
        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        for old in AVATAR_DIR.glob('avatar.*'):
            if old.is_file():
                old.unlink(missing_ok=True)
        (AVATAR_DIR / f'avatar{ext}').write_bytes(data)
    except OSError:
        # 目录不可写（例如部署在只读文件系统）时给出提示，而不是 500
        return redirect(_with_param(back, 'avatar_error', 'save'))
    return redirect(_with_param(back, 'avatar_ok', '1'))


# ---------------- 代码统计（原功能） ----------------

LANGUAGE_MAPPING = {
    ".py": {"name": "Python", "single_comment": "#", "block_comment": ('"""', '"""')},
    ".java": {"name": "Java", "single_comment": "//", "block_comment": ('/*', '*/')},
    ".cpp": {"name": "C++", "single_comment": "//", "block_comment": ('/*', '*/')},
    ".c": {"name": "C", "single_comment": "//", "block_comment": ('/*', '*/')},
    ".h": {"name": "C", "single_comment": "//", "block_comment": ('/*', '*/')},
}

IGNORED_DIRS = {'.venv', 'venv', '.git', '__pycache__', 'node_modules',
                'build', 'dist', '.idea', '.vscode'}


def is_binary_file(file_path):
    try:
        with open(file_path, 'rb') as f:
            if b'\x00' in f.read(1024):
                return True
    except Exception:
        return True
    return False


def count_lines_in_file(file_path, lang_config):
    total_lines = blank_lines = comment_lines = code_lines = 0
    single_prefix = lang_config["single_comment"]
    block_start, block_end = lang_config["block_comment"]
    in_block_comment = False
    try:
        with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
            for line in f:
                total_lines += 1
                stripped = line.strip()
                if not stripped:
                    blank_lines += 1
                    continue
                if in_block_comment:
                    comment_lines += 1
                    if block_end in stripped:
                        in_block_comment = False
                    continue
                if block_start and block_end and block_start in stripped and block_end not in stripped:
                    if stripped.startswith(block_start):
                        comment_lines += 1
                        in_block_comment = True
                        continue
                if single_prefix and stripped.startswith(single_prefix):
                    comment_lines += 1
                    continue
                code_lines += 1
        return total_lines, blank_lines, comment_lines, code_lines
    except Exception:
        return 0, 0, 0, 0


def analyze_directory(dir_path):
    results = {}
    path = Path(dir_path)
    total_files_scanned = 0
    for file_path in path.rglob('*'):
        if any(part in IGNORED_DIRS for part in file_path.parts):
            continue
        if file_path.is_file():
            total_files_scanned += 1
            suffix = file_path.suffix.lower()
            if suffix in LANGUAGE_MAPPING:
                lang_config = LANGUAGE_MAPPING[suffix]
                lang_name = lang_config["name"]
                if lang_name not in results:
                    results[lang_name] = {"files": 0, "code": 0, "blank": 0, "comment": 0}
                results[lang_name]["files"] += 1
                if is_binary_file(file_path):
                    continue
                _, b, c, code = count_lines_in_file(file_path, lang_config)
                results[lang_name]["code"] += code
                results[lang_name]["blank"] += b
                results[lang_name]["comment"] += c
    return results, total_files_scanned


# ---------------- GitHub 仓库统计 ----------------

MAX_REPO_DOWNLOAD = 50 * 1024 * 1024  # 与 MAX_CONTENT_LENGTH 保持一致

# 匹配 https://github.com/owner/repo、SSH git@github.com:owner/repo、owner/repo
GITHUB_REPO_RE = re.compile(r'github\.com[/:]([^/]+)/([^/#?]+)', re.IGNORECASE)


def safe_extract(zip_ref, dest_dir):
    """安全解压：逐条校验路径，防止 zip 内恶意路径穿越（zip-slip）。"""
    dest_root = Path(dest_dir).resolve()
    for member in zip_ref.infolist():
        target = (dest_root / member.filename).resolve()
        if not str(target).startswith(str(dest_root)):
            raise ValueError(f"非法的压缩包路径: {member.filename}")
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with zip_ref.open(member) as src, open(target, 'wb') as dst:
                shutil.copyfileobj(src, dst)


def parse_repo_url(url):
    """从 GitHub 链接解析出 (owner, repo)。解析失败时返回 (None, None)。"""
    m = GITHUB_REPO_RE.search(url)
    if m:
        return m.group(1), m.group(2).removesuffix('.git')
    parts = url.strip().strip('/').split('/')
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0], parts[1].removesuffix('.git')
    return None, None


def _http_get_json(url, timeout=15):
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'code-counter/1.0',
                 'Accept': 'application/vnd.github+json'},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def download_repo_zip(owner, repo, branch, dest_path, max_bytes=MAX_REPO_DOWNLOAD):
    """从 codeload 下载指定分支的源码 zip，超过大小限制则中断。"""
    url = f'https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{branch}'
    req = urllib.request.Request(url, headers={'User-Agent': 'code-counter/1.0'})
    total = 0
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest_path, 'wb') as f:
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError('仓库超过 50MB 大小限制，无法统计')
            f.write(chunk)


def fetch_repo_zip(owner, repo, dest_path):
    """下载仓库默认分支源码。优先用 GitHub API 查默认分支，失败时回退尝试 main/master。"""
    candidates = []
    try:
        data = _http_get_json(f'https://api.github.com/repos/{owner}/{repo}')
        candidates.append(data.get('default_branch'))
    except Exception:
        pass
    for branch in ('main', 'master'):
        if branch not in candidates:
            candidates.append(branch)

    last_err = None
    for branch in candidates:
        if not branch:
            continue
        try:
            download_repo_zip(owner, repo, branch, dest_path)
            return
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code != 404:  # 非 404（如限流 403）直接抛出
                raise
        except ValueError:
            raise
    raise ValueError(f'仓库不存在或下载失败（{last_err and last_err.code}），'
                     '请确认链接为公开仓库且名称正确')


# ---------------- 原路由 ----------------

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/profile')
def profile_detail():
    return render_template('profile.html')


@app.route('/projects')
def projects():
    return render_template('projects.html')


@app.route('/projects/code-counter', methods=['GET', 'POST'])
def code_counter():
    results = None
    totals = None
    filename = None
    if request.method == 'POST':
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename.endswith('.zip'):
                with tempfile.TemporaryDirectory() as temp_dir:
                    zip_path = os.path.join(temp_dir, 'uploaded.zip')
                    file.save(zip_path)
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        safe_extract(zip_ref, temp_dir)
                    results, total_files = analyze_directory(temp_dir)
                    totals = {
                        "files": sum(d['files'] for d in results.values()),
                        "code": sum(d['code'] for d in results.values()),
                        "blank": sum(d['blank'] for d in results.values()),
                        "comment": sum(d['comment'] for d in results.values()),
                        "total_scanned": total_files,
                    }
                    filename = file.filename
    return render_template('code_counter.html', results=results,
                           totals=totals, filename=filename)


@app.route('/projects/github-counter', methods=['GET', 'POST'])
def github_counter():
    """通过 GitHub 仓库链接统计代码量。仅支持公开仓库。"""
    results = None
    totals = None
    repo_label = None
    error = None
    if request.method == 'POST':
        repo_url = request.form.get('repo_url', '').strip()
        owner, repo = parse_repo_url(repo_url)
        if not owner or not repo:
            error = '无法识别 GitHub 仓库链接，请使用类似 https://github.com/owner/repo 的格式'
        else:
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    zip_path = os.path.join(temp_dir, 'repo.zip')
                    fetch_repo_zip(owner, repo, zip_path)
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        safe_extract(zip_ref, temp_dir)
                    results, total_files = analyze_directory(temp_dir)
                    totals = {
                        "files": sum(d['files'] for d in results.values()),
                        "code": sum(d['code'] for d in results.values()),
                        "blank": sum(d['blank'] for d in results.values()),
                        "comment": sum(d['comment'] for d in results.values()),
                        "total_scanned": total_files,
                    }
                    repo_label = f"{owner}/{repo}"
            except ValueError as e:
                error = str(e)
            except Exception:
                error = '统计失败，请稍后重试'
    return render_template('github_counter.html', results=results,
                           totals=totals, repo=repo_label, error=error)


# ---------------- 注册蓝图 ----------------

if 'math_practice' not in app.blueprints:
    app.register_blueprint(math_bp)

if 'game_24' not in app.blueprints:
    app.register_blueprint(game24_bp)

if 'dice_game' not in app.blueprints:
    app.register_blueprint(dice_bp)


# ---------------- 启动 ----------------

if __name__ == '__main__':
    with app.app_context():
        init_question_bank(count=10000, batch=500)
    app.run(host='0.0.0.0', debug=True, port=5000)