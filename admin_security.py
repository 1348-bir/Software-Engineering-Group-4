"""共享数据写入的两种校验：管理员口令与 CSRF 令牌。

头像上传、题库批量生成会改动所有人可见的数据，因此需要口令；
其中的表单提交再加一道 CSRF，防止别的站点替用户发请求。
口令来自环境变量 STUDIO_ADMIN_TOKEN，未配置时相关接口一律 403。
"""
import hmac
import secrets

from flask import abort, current_app, request, session


def require_admin(token=None):
    """校验管理员口令；口令可以放在表单字段里，也可以放在 Bearer 头里。

    使用 ``hmac.compare_digest`` 做常量时间比较，避免通过响应时间猜口令。
    """
    expected = current_app.config.get('STUDIO_ADMIN_TOKEN', '')
    if token is None:
        authorization = request.headers.get('Authorization', '')
        token = authorization.removeprefix('Bearer ') if authorization.startswith('Bearer ') else ''
    if not expected or not isinstance(token, str) or not hmac.compare_digest(
            token.encode('utf-8'), expected.encode('utf-8')):
        abort(403)


def csrf_token():
    """为当前会话生成并复用 CSRF 令牌，供表单隐藏字段使用。"""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(32)
    return session['csrf_token']


def require_csrf():
    """比对表单提交的 CSRF 令牌与会话中保存的值，不一致则 403。"""
    expected = session.get('csrf_token', '')
    supplied = request.form.get('csrf_token', '')
    if not expected or not hmac.compare_digest(expected.encode(), supplied.encode()):
        abort(403)
