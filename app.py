"""Flask 应用入口：全局配置、页面路由、三个功能蓝图与成员站点路由。

四类功能（代码统计、数学练习、24 点、双骰）都在同一个进程里提供：
- 统计功能直接写在本文件与 ``code_stats`` / ``url_source`` 中；
- 数学、24 点、骰子各自是蓝图，末尾统一注册；
- 成员页与旧入口兼容路由由 ``group_site`` 注册。
"""
import faulthandler
import os
from pathlib import Path
from flask import Flask, jsonify, redirect, render_template, request, url_for

# 原生扩展（tree-sitter 等）崩溃时，把各线程的 Python 栈直接打到控制台，
# 方便定位是哪个请求、哪一行触发的，否则进程会静默消失。
faulthandler.enable()

from code_stats import (
    analyze_uploads,
    MAX_REQUEST,
    MAX_UPLOAD,
    MAX_FILES,
    MAX_UPLOAD_FORM_PARTS,
)
from url_source import analyze_url

app = Flask(__name__)
# MAX_CONTENT_LENGTH：整个请求体上限（文件量 + 4 MB 表单开销）；
# MAX_FORM_PARTS：multipart 部件数上限，防止大量小文件撑爆解析器。
app.config.update(MAX_CONTENT_LENGTH=MAX_REQUEST, MAX_FORM_PARTS=MAX_UPLOAD_FORM_PARTS,
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
def local_session_key():
    """Keep local practice identities stable across app restarts."""
    key_path = Path(app.instance_path) / 'session.key'
    key_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with key_path.open('xb') as output:
            output.write(os.urandom(32))
    except FileExistsError:
        pass
    key = key_path.read_bytes()
    if len(key) != 32:
        raise RuntimeError('本地会话密钥无效，请检查 instance/session.key')
    return key


app.secret_key = os.environ.get('SECRET_KEY') or local_session_key()
# 管理员口令默认为空，未设置时头像上传与题库生成接口直接 403。
app.config['STUDIO_ADMIN_TOKEN'] = os.environ.get('STUDIO_ADMIN_TOKEN', '')
app.config['MUSEUM_ADMIN_PASSWORD'] = os.environ.get('MUSEUM_ADMIN_PASSWORD', '')
app.config['MUSEUM_DATA_DIR'] = os.environ.get('MUSEUM_DATA_DIR') or str(Path(__file__).resolve().parent / 'museum' / 'data')


@app.get('/')
def index():
    """小组主页：Hero、成员卡片、工具箱与关于区块。"""
    return render_template('home.html')


@app.get('/history')
def history():
    """练习记录总入口，分模块链接到数学、24 点与骰子的历史页。"""
    return render_template('history.html')


@app.get('/arithmetic')
@app.post('/arithmetic/submit')
def legacy_arithmetic():
    """旧版四则运算入口（含旧提交地址），303 跳转到统一的数学练习页。"""
    return redirect(url_for('math_practice.practice'), code=303)


@app.get('/game24')
@app.get('/game24/solution')
@app.post('/game24/check')
def legacy_game24():
    """旧版 24 点入口及其解法/判题地址，统一跳转到新页面。"""
    return redirect(url_for('game_24.play'), code=303)


@app.context_processor
def inject_profile():
    """模板上下文注入：把 team.json 与成员头像地址提供给所有模板。"""
    from group_site import load_team, member_avatar  # 延迟导入，避免循环依赖

    team = load_team()
    for member in team['members']:
        member['avatar_url'] = member_avatar(member['id'])
    return {'profile': team, 'team': team,
            'upload_limit': MAX_UPLOAD, 'max_files': MAX_FILES}


@app.get('/code-stats')
def code_stats():
    """代码统计页面；表单与结果区由 static/stats.js 驱动。"""
    return render_template('code_stats.html')


@app.get('/math')
def math_home():
    """趣味数学导航页，链接到练习、24 点与小游戏。"""
    return render_template('math.html')


@app.get('/code-compare')
def code_compare_page():
    return render_template('code_compare.html')


@app.post('/api/compare')
def code_compare_api():
    from version_compare import compare_uploads
    request.max_form_parts = MAX_UPLOAD_FORM_PARTS
    before, after = request.files.getlist('before'), request.files.getlist('after')
    if not before or not after or not all(f.filename for f in before + after):
        return jsonify(error='请分别选择旧版本和新版本代码'), 400
    try:
        from code_stats import stream_size, MAX_TOTAL
        if sum(stream_size(f.stream) for f in before + after) > MAX_TOTAL:
            raise ValueError('两个版本合计上传大小不能超过 1 GB')
        return jsonify(compare_uploads(before, after, request.form.get('strip_root', '1') == '1'))
    except (ValueError, MemoryError) as exc:
        return jsonify(error=str(exc) or '文件过大，请缩小比较范围'), 400


@app.post('/api/analyze')
def analyze():
    """上传统计接口：接收文件/文件夹/ZIP，交给统计引擎并返回 JSON 报告。"""
    # 单独放宽本接口的部件数上限，允许一次上传上万个文件。
    request.max_form_parts = MAX_UPLOAD_FORM_PARTS
    uploads = request.files.getlist('files')
    if not uploads or all(not f.filename for f in uploads):
        return jsonify(error='请先选择代码文件、文件夹或 ZIP'), 400
    try:
        return jsonify(analyze_uploads(uploads))
    except ValueError as exc:
        # 引擎用 ValueError 表达可预期的输入错误（超限、编码、ZIP 损坏等）。
        return jsonify(error=str(exc)), 400
    except MemoryError:
        # 超大源码在读取/词法分析时可能吃光内存，返回可读提示而不是 500 页面。
        return jsonify(error='文件过大导致内存不足，请缩小文件范围后重试'), 400


@app.errorhandler(413)
def upload_too_large(error):
    """请求体超出 MAX_CONTENT_LENGTH 时返回可读的 JSON 而不是默认页面。"""
    return jsonify(error='上传请求过大或文件过多；文件总大小上限为 1 GB，请分批统计'), 413


@app.errorhandler(500)
def internal_error(error):
    """未预料的异常也返回 JSON，前端才能把原因显示出来而不是“没有有效结果”。"""
    app.logger.exception('处理请求时发生未捕获异常')
    return jsonify(error='服务器处理失败，请缩小文件范围后重试（详细堆栈见服务端控制台）'), 500


@app.post('/api/analyze-url')
def analyze_remote_source():
    """网址统计接口：校验 JSON 请求体后抓取公开源码并统计。"""
    # 本接口只需要一个很短的 URL 字段，因此把请求体限制在 16 KB。
    request.max_content_length = 16 * 1024
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='请填写需要统计的网址'), 400
    try:
        return jsonify(analyze_url(data.get('url')))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


# 蓝图放在末尾导入并注册：此时 app 已配置完成，避免循环导入。
from math_practice import bp as math_practice_bp  # noqa: E402
from game_24 import bp as game24_bp  # noqa: E402
from dice_game import bp as dice_bp  # noqa: E402

app.register_blueprint(math_practice_bp)
app.register_blueprint(game24_bp)
app.register_blueprint(dice_bp)

from group_site import register_group_routes  # noqa: E402

register_group_routes(app)

from museum import bp as museum_bp
app.register_blueprint(museum_bp)


def _port_in_use(host, port):
    """探测端口是否已被占用：Windows 下两个 Flask 实例可以同时绑定同一端口，
    导致一个带 OCR、一个不带 OCR，请求随机落到不同进程，很难排查。"""
    import socket

    probe = '127.0.0.1' if host in ('0.0.0.0', '::', '') else host
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((probe, port)) == 0


def run():
    host = os.environ.get('STUDIO_HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '5050'))
    if _port_in_use(host, port):
        raise SystemExit(
            f'端口 {host}:{port} 已被占用：可能已经有一个实例在运行，'
            '请先关闭旧进程（或换一个 PORT）再启动。')
    app.run(host=host, port=port, debug=False)

if __name__ == '__main__':
    run()
