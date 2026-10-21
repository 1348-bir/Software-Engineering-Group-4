"""Group members, avatars and backwards-compatible project links."""
import json
import re
from pathlib import Path
from uuid import uuid4
from flask import abort, redirect, render_template, request, url_for
from code_stats import analyze_uploads
from url_source import analyze_url

ROOT = Path(__file__).resolve().parent
AVATAR_DIR = ROOT / 'static' / 'uploads'
AVATAR_LIMIT = 3 * 1024 * 1024
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}


def load_team():
    return json.loads((ROOT / 'team.json').read_text(encoding='utf-8'))


def member_avatar(member_id):
    if not AVATAR_DIR.is_dir():
        return None
    images = [p for p in AVATAR_DIR.glob(member_id + '-*') if p.suffix.lower() in IMAGE_EXTENSIONS]
    if not images and member_id == 'wen-jingxiong':
        images = [p for p in AVATAR_DIR.glob('avatar.*') if p.suffix.lower() in IMAGE_EXTENSIONS]
    if not images:
        return None
    image = max(images, key=lambda p: p.stat().st_mtime_ns)
    return url_for('static', filename='uploads/' + image.name)


def register_group_routes(app):
    app.add_url_rule('/', endpoint='index', view_func=app.view_functions['home'])

    @app.get('/members')
    def members():
        return render_template('members.html')

    @app.get('/profile')
    def profile_detail():
        return redirect(url_for('members'))

    @app.get('/members/<member_id>')
    def member_detail(member_id):
        member = next((m for m in load_team()['members'] if m['id'] == member_id), None)
        if member is None:
            abort(404)
        member['avatar_url'] = member_avatar(member_id)
        return render_template('member_detail.html', member=member)

    @app.get('/members/wen-jingxiong/original-profile')
    def original_wen_profile():
        return render_template('profile.html', avatar_url=member_avatar('wen-jingxiong'))

    @app.post('/avatar/upload')
    def upload_avatar():
        request.max_content_length = AVATAR_LIMIT + 64 * 1024
        member_id = request.form.get('member_id', 'wen-jingxiong')
        if member_id not in {m['id'] for m in load_team()['members']}:
            abort(400)
        target = url_for('member_detail', member_id=member_id)
        file = request.files.get('avatar')
        if file is None or not file.filename:
            return redirect(target)
        extension = Path(file.filename).suffix.lower()
        data = file.read(AVATAR_LIMIT + 1)
        if extension not in IMAGE_EXTENSIONS:
            return redirect(target + '?avatar_error=format')
        if not data or len(data) > AVATAR_LIMIT:
            return redirect(target + '?avatar_error=size')
        signatures = (b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff', b'GIF87a', b'GIF89a', b'BM')
        valid_image = any(data.startswith(signature) for signature in signatures)
        valid_image = valid_image or (data.startswith(b'RIFF') and data[8:12] == b'WEBP')
        if not valid_image:
            return redirect(target + '?avatar_error=format')
        try:
            AVATAR_DIR.mkdir(parents=True, exist_ok=True)
            destination = AVATAR_DIR / f'{member_id}-{uuid4().hex}{extension}'
            destination.write_bytes(data)
            for previous in AVATAR_DIR.glob(member_id + '-*'):
                if previous != destination and previous.suffix.lower() in IMAGE_EXTENSIONS:
                    previous.unlink()
        except OSError:
            return redirect(target + '?avatar_error=save')
        return redirect(target + '?avatar_ok=1')

    @app.get('/projects')
    def projects():
        return render_template('projects_group.html')

    @app.route('/projects/code-counter', methods=['GET', 'POST'])
    def code_counter():
        if request.method == 'GET':
            return redirect(url_for('code_stats'))
        uploads = request.files.getlist('file') or request.files.getlist('files')
        try:
            if not uploads:
                raise ValueError('请先选择代码文件或 ZIP')
            report = analyze_uploads(uploads)
            return render_template('code_stats.html', initial_stats={'report': report, 'source': 'files'})
        except ValueError as exc:
            return render_template('code_stats.html', initial_stats={'error': str(exc), 'source': 'files'}), 400

    @app.route('/projects/github-counter', methods=['GET', 'POST'])
    def github_counter():
        if request.method == 'GET':
            return redirect(url_for('code_stats') + '#url-title')
        value = request.form.get('repo_url', '').strip()
        short = value.removeprefix('git@github.com:').removesuffix('.git')
        if re.fullmatch(r'[\w.-]+/[\w.-]+', short):
            value = 'https://github.com/' + short
        try:
            report = analyze_url(value)
            return render_template('code_stats.html', initial_stats={'report': report, 'source': 'url', 'url': value})
        except ValueError as exc:
            return render_template('code_stats.html', initial_stats={'error': str(exc), 'source': 'url', 'url': value}), 400
