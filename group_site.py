"""小组成员、头像上传与旧入口兼容路由。

这里的路由都注册在主应用上（不是蓝图），因为成员页要用到 app 级的
context_processor，旧入口则依赖主应用上的端点名（code_stats / math_practice 等）。

成员资料全部来自 team.json，改内容不需要改模板；
头像按成员独立保存，只允许管理员口令 + CSRF 校验过的上传。
"""
import json
import re
from pathlib import Path
from uuid import uuid4

from flask import abort, redirect, render_template, request, url_for

from code_stats import analyze_uploads, MAX_UPLOAD_FORM_PARTS
from url_source import analyze_url
from admin_security import csrf_token, require_admin, require_csrf

ROOT = Path(__file__).resolve().parent
AVATAR_DIR = ROOT / 'static' / 'uploads'
AVATAR_LIMIT = 3 * 1024 * 1024      # 头像大小上限 3 MB
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}


def load_team():
    """读取并解析 team.json（组名、成员、技能、仓库地址等）。"""
    return json.loads((ROOT / 'team.json').read_text(encoding='utf-8'))


def member_avatar(member_id):
    """返回该成员最新头像的 URL；没有头像文件时返回 None。"""
    if not AVATAR_DIR.is_dir():
        return None
    images = [p for p in AVATAR_DIR.glob(member_id + '-*') if p.suffix.lower() in IMAGE_EXTENSIONS]
    # 兼容老仓库留下的 avatar.* 通用头像（只给文敬雄兜底）。
    if not images and member_id == 'wen-jingxiong':
        images = [p for p in AVATAR_DIR.glob('avatar.*') if p.suffix.lower() in IMAGE_EXTENSIONS]
    if not images:
        return None
    image = max(images, key=lambda p: p.stat().st_mtime_ns)   # 按修改时间取最新一张
    return url_for('static', filename='uploads/' + image.name)


def register_group_routes(app):
    """把所有成员/项目相关路由注册到传入的 app 上。"""

    @app.get('/members')
    def members():
        """成员列表页：从 team.json 渲染成员卡片。"""
        return render_template('members.html')

    @app.get('/profile')
    def profile_detail():
        """旧的个人主页地址，统一重定向到成员页。"""
        return redirect(url_for('members'))

    @app.get('/members/<member_id>')
    def member_detail(member_id):
        """成员详情页；id 不存在时返回 404。"""
        member = next((m for m in load_team()['members'] if m['id'] == member_id), None)
        if member is None:
            abort(404)
        member['avatar_url'] = member_avatar(member_id)
        return render_template('member_detail.html', member=member, csrf_token=csrf_token())

    @app.get('/members/wen-jingxiong/original-profile')
    def original_wen_profile():
        """保留原仓库中文敬雄的详细档案页，内容与新版成员页并存。"""
        return render_template('profile.html',
                               avatar_url=member_avatar('wen-jingxiong'),
                               csrf_token=csrf_token())

    @app.post('/avatar/upload')
    def upload_avatar():
        """头像上传：管理员口令 → CSRF → 成员校验 → 扩展名/大小/文件头校验 → 落盘。"""
        # 只允许 3 MB 图片再加一点点表单开销，避免大文件占用内存。
        request.max_content_length = AVATAR_LIMIT + 64 * 1024
        require_admin(request.form.get('admin_token', ''))
        require_csrf()
        member_id = request.form.get('member_id', 'wen-jingxiong')
        if member_id not in {m['id'] for m in load_team()['members']}:
            abort(400)
        target = url_for('member_detail', member_id=member_id)
        file = request.files.get('avatar')
        if file is None or not file.filename:
            return redirect(target)
        extension = Path(file.filename).suffix.lower()
        # 多读 1 字节，用来判断是否超过上限。
        data = file.read(AVATAR_LIMIT + 1)
        if extension not in IMAGE_EXTENSIONS:
            return redirect(target + '?avatar_error=format')
        if not data or len(data) > AVATAR_LIMIT:
            return redirect(target + '?avatar_error=size')
        # 光看扩展名不够：再按文件头（魔数）确认真的是图片。
        signatures = (b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff', b'GIF87a', b'GIF89a', b'BM')
        valid_image = any(data.startswith(signature) for signature in signatures)
        valid_image = valid_image or (data.startswith(b'RIFF') and data[8:12] == b'WEBP')
        if not valid_image:
            return redirect(target + '?avatar_error=format')
        try:
            AVATAR_DIR.mkdir(parents=True, exist_ok=True)
            # 文件名带随机串，既能避免覆盖，也能绕过浏览器缓存。
            destination = AVATAR_DIR / f'{member_id}-{uuid4().hex}{extension}'
            destination.write_bytes(data)
            # 写入成功后清理该成员的旧头像，避免目录越堆越多。
            for previous in AVATAR_DIR.glob(member_id + '-*'):
                if previous != destination and previous.suffix.lower() in IMAGE_EXTENSIONS:
                    previous.unlink()
        except OSError:
            return redirect(target + '?avatar_error=save')
        return redirect(target + '?avatar_ok=1')

    @app.get('/projects')
    def projects():
        """小组项目总览：六张工具卡片。"""
        return render_template('projects_group.html')

    @app.route('/projects/code-counter', methods=['GET', 'POST'])
    def code_counter():
        """旧版代码统计入口：GET 跳转，POST 直接复用统计引擎并渲染结果。"""
        if request.method == 'GET':
            return redirect(url_for('code_stats'))
        request.max_form_parts = MAX_UPLOAD_FORM_PARTS
        uploads = request.files.getlist('file') or request.files.getlist('files')
        try:
            if not uploads:
                raise ValueError('请先选择代码文件或 ZIP')
            report = analyze_uploads(uploads)
            return render_template('code_stats.html',
                                   initial_stats={'report': report, 'source': 'files'})
        except ValueError as exc:
            return render_template('code_stats.html',
                                   initial_stats={'error': str(exc), 'source': 'files'}), 400

    @app.route('/projects/github-counter', methods=['GET', 'POST'])
    def github_counter():
        """旧版 GitHub 统计入口：把 owner/repo 或 git@ 地址规整成网址再统计。"""
        if request.method == 'GET':
            return redirect(url_for('code_stats') + '#url-title')
        value = request.form.get('repo_url', '').strip()
        # 兼容「git@github.com:owner/repo.git」与「owner/repo」两种简写。
        short = value.removeprefix('git@github.com:').removesuffix('.git')
        if re.fullmatch(r'[\w.-]+/[\w.-]+', short):
            value = 'https://github.com/' + short
        try:
            report = analyze_url(value)
            return render_template('code_stats.html',
                                   initial_stats={'report': report, 'source': 'url', 'url': value})
        except ValueError as exc:
            return render_template('code_stats.html',
                                   initial_stats={'error': str(exc), 'source': 'url', 'url': value}), 400
