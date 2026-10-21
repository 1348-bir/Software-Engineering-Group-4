"""Explicit admin credentials for shared-data writes; disabled by default."""
import hmac
import secrets

from flask import abort, current_app, request, session


def require_admin(token=None):
    expected = current_app.config.get('STUDIO_ADMIN_TOKEN', '')
    if token is None:
        authorization = request.headers.get('Authorization', '')
        token = authorization.removeprefix('Bearer ') if authorization.startswith('Bearer ') else ''
    if not expected or not isinstance(token, str) or not hmac.compare_digest(
            token.encode('utf-8'), expected.encode('utf-8')):
        abort(403)


def csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(32)
    return session['csrf_token']


def require_csrf():
    expected = session.get('csrf_token', '')
    supplied = request.form.get('csrf_token', '')
    if not expected or not hmac.compare_digest(expected.encode(), supplied.encode()):
        abort(403)
