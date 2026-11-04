"""Museum exhibit administration and playback mounted in the group site."""
import datetime as dt
import hmac
import os
from pathlib import Path
import secrets
import shutil
import threading
import tempfile

from flask import Blueprint, Response, current_app, jsonify, request, send_file, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge

from .catalog import LIMIT, MEDIA, ROOT, Store, feed, string, update
from .documents import DOCUMENT_LIMIT, FORMATS, render

bp = Blueprint('museum', __name__, url_prefix='/museum')
WEB = ROOT / 'web'
_store_lock = threading.Lock()
PAGES = {'app.js', 'style.css', 'admin.js', 'terminal.js', 'control.css'}


def store():
    with _store_lock:
        ext = current_app.extensions
        if 'museum_catalog' not in ext:
            ext['museum_catalog'] = Store(current_app.config['MUSEUM_DATA_DIR'])
        return ext['museum_catalog']


def admin_auth():
    expected = current_app.config.get('MUSEUM_ADMIN_PASSWORD', '')
    if not expected:
        return Response('展播后台未启用。请设置 MUSEUM_ADMIN_PASSWORD 环境变量后重启网站。',
                        503, content_type='text/plain; charset=utf-8')
    auth = request.authorization
    supplied = auth.password if auth and auth.type == 'basic' and auth.username == 'admin' else ''
    if not hmac.compare_digest((supplied or '').encode(), expected.encode()):
        return Response('请使用展播管理员账号登录。', 401,
                        headers={'WWW-Authenticate':'Basic realm="Museum Control", charset="UTF-8"'},
                        content_type='text/plain; charset=utf-8')
    return None


@bp.after_request
def response_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    if request.endpoint in {'museum.admin', 'museum.admin_api', 'museum.terminal_feed', 'museum.document_preview'}:
        response.headers['Cache-Control'] = 'no-store'
    return response


@bp.get('/')
def index():
    return send_from_directory(WEB, 'index.html')


@bp.get('/admin')
def admin():
    error = admin_auth()
    return error if error is not None else send_from_directory(WEB, 'admin.html')


@bp.get('/terminal')
def terminal():
    return send_from_directory(WEB, 'terminal.html')


@bp.get('/<name>')
def assets(name):
    if name not in PAGES:
        return jsonify(error='页面不存在'), 404
    return send_from_directory(WEB, name)


@bp.get('/api/feed')
def terminal_feed():
    catalog = store()
    try:
        with catalog.lock:
            data = feed(catalog.data, request.args.get('id', ''), dt.datetime.now())
        return jsonify(data)
    except KeyError:
        return jsonify(error='终端未登记或已删除'), 404


@bp.get('/media/<key>')
def media(key):
    catalog = store()
    with catalog.lock:
        asset = catalog.data['assets'].get(key)
    if asset is None:
        return jsonify(error='素材不存在'), 404
    if asset['ext'] in FORMATS:
        error = admin_auth()
        if error is not None:
            return error
    path = catalog.media / (key + asset['ext'])
    if not path.is_file():
        return jsonify(error='素材文件不存在'), 404
    return send_file(path, mimetype=asset['mime'], conditional=True, max_age=0,
                     as_attachment=asset['ext'] in FORMATS, download_name=asset['name'] + asset['ext']
                     if asset['ext'] in FORMATS and not asset['name'].lower().endswith(asset['ext']) else asset['name'])


@bp.get('/media/<key>/page/<int:page>')
def document_page(key, page):
    catalog = store()
    with catalog.lock:
        item = catalog.data['assets'].get(key)
    if item is None or not 1 <= page <= item.get('page_count', 0):
        return jsonify(error='文档页面不存在'), 404
    return send_from_directory(catalog.media / (key + '-pages'), f'{page}.png',
                               mimetype='image/png', max_age=3600)


@bp.get('/api/document/<key>')
def document_preview(key):
    catalog = store()
    with catalog.lock:
        item = catalog.data['assets'].get(key)
    if item is None or not item.get('page_count'):
        return jsonify(error='文档不存在'), 404
    return jsonify(terminal={'name':item['name'], 'group':'文档预览'}, plan=key, layout='single',
                   regions=[[dict(item, url='/museum/media/'+key)]], tickers=[])


def upload(catalog):
    name = string(request.args.get('name', ''), 240, True)
    ext = Path(name).suffix.lower()
    mime = MEDIA.get(ext) or FORMATS.get(ext)
    if mime is None:
        raise ValueError('不支持该文件格式')
    cap = DOCUMENT_LIMIT if ext in FORMATS else 5 * 1024**2 if mime == 'text/plain' else LIMIT
    request.max_content_length = cap
    size = request.content_length
    if size is None or size <= 0:
        raise ValueError('请上传非空文件')
    if size > cap:
        raise RequestEntityTooLarge()
    key = secrets.token_hex(12)
    path = catalog.media / (key + ext)
    pages_path = catalog.media / (key + '-pages')
    item = {'id':key,'name':name,'ext':ext,'mime':mime,'size':size,'category':'未分类',
            'subtitle':'','watermark':'','duration':10}
    with tempfile.TemporaryDirectory(prefix='upload-', dir=catalog.directory) as scratch:
        temp = Path(scratch) / ('source' + ext)
        remain = size
        with temp.open('xb') as fh:
            while remain:
                chunk = request.stream.read(min(remain, 1024**2))
                if not chunk:
                    raise ValueError('上传中断')
                fh.write(chunk)
                remain -= len(chunk)
        if mime == 'text/plain':
            temp.read_text(encoding='utf-8-sig')
        if ext in FORMATS:
            preview = Path(scratch) / 'pages'
            item['page_count'] = render(temp, preview)
        with catalog.lock:
            try:
                os.replace(temp, path)
                if 'page_count' in item:
                    os.replace(preview, pages_path)
                catalog.commit({**catalog.data, 'assets':{**catalog.data['assets'], key:item}})
            except OSError:
                path.unlink(missing_ok=True)
                shutil.rmtree(pages_path, ignore_errors=True)
                raise
    return jsonify(item), 201


@bp.errorhandler(413)
def too_large(_error):
    return jsonify(error='素材上传超过上限：图片与视频 1 GB，Office 文档 50 MB，文本 5 MB，管理请求 1 MB'), 413


@bp.route('/api/admin/<kind>', methods=['GET', 'POST', 'DELETE'])
def admin_api(kind):
    error = admin_auth()
    if error is not None:
        return error
    if request.method != 'GET' and request.headers.get('X-Museum-Request') != '1':
        return jsonify(error='请从管理后台提交'), 403
    catalog = store()
    try:
        if request.method == 'GET' and kind == 'catalog':
            with catalog.lock:
                return jsonify(catalog.data)
        if request.method == 'POST' and kind == 'upload':
            return upload(catalog)
        if kind not in catalog.data or request.method not in ('POST', 'DELETE'):
            return jsonify(error='接口不存在'), 404
        request.max_content_length = 1024**2
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            return jsonify(error='需要 JSON 对象'), 400
        with catalog.lock:
            data = {**catalog.data, kind:dict(catalog.data[kind])}
            if request.method == 'POST':
                item = update(kind, value, data)
                data[kind][item['id']] = item
            else:
                key = value['id']
                if kind == 'assets' and any(key in ids for plan in data['plans'].values() for ids in plan['regions']):
                    raise ValueError('素材仍被播放计划使用，请先修改或删除计划')
                item = data[kind].pop(key)
            catalog.commit(data)
            if request.method == 'DELETE' and kind == 'assets':
                try:
                    (catalog.media / (item['id'] + item['ext'])).unlink(missing_ok=True)
                    if item.get('page_count'):
                        shutil.rmtree(catalog.media / (item['id'] + '-pages'), ignore_errors=True)
                except OSError:
                    current_app.logger.warning('Could not remove museum media %s', item['id'])
        return jsonify(item)
    except KeyError:
        return jsonify(error='记录不存在或缺少必填字段'), 404
    except (ValueError, TypeError, AttributeError) as exc:
        return jsonify(error=str(exc)), 400
