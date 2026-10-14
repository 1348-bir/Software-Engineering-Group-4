# dice_game/routes.py
import os
import uuid

from flask import Blueprint, render_template, request, jsonify, session

from .engine import roll_dice, is_win
from .db import DiceDB
from .i18n import get_lang, translator

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

bp = Blueprint(
    'dice_game',
    __name__,
    url_prefix='/dice',
    template_folder=os.path.join(BASE_DIR, 'templates', 'dice_game'),
    static_folder=os.path.join(BASE_DIR, 'static', 'dice_game'),
    static_url_path='/static/dice_game',
)

db = DiceDB()


def current_user():
    if 'uid' not in session:
        session['uid'] = uuid.uuid4().hex[:16]
    return session['uid']


# ---------------- 页面路由 ----------------

@bp.route('/')
def play():
    lang = get_lang(request)
    tr = translator(lang)
    return render_template('dice_game/play.html', t=tr, lang=lang)


@bp.route('/history')
def history():
    lang = get_lang(request)
    tr = translator(lang)
    uid = current_user()
    attempts = db.recent_attempts(uid, limit=100)
    stats = db.stats(uid)
    return render_template('dice_game/history.html', t=tr, lang=lang,
                           attempts=attempts, stats=stats)


# ---------------- API ----------------

@bp.route('/api/roll', methods=['POST'])
def api_roll():
    """掷两个骰子，记录结果，返回点数与是否获胜"""
    d1, d2 = roll_dice()
    win = is_win(d1, d2)

    uid = current_user()
    db.add_attempt(uid, d1, d2, win)

    return jsonify({
        'd1': d1,
        'd2': d2,
        'total': d1 + d2,
        'win': win,
    })


@bp.route('/api/history')
def api_history():
    uid = current_user()
    after_id = int(request.args.get('after', 0))
    rows = db.recent_attempts(uid, limit=50)
    new_rows = [r for r in rows if r['id'] > after_id]
    stats = db.stats(uid)
    return jsonify({
        'attempts': new_rows,
        'stats': stats,
        'latest_id': rows[0]['id'] if rows else after_id,
    })
