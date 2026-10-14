# game_24/routes.py
import os
import uuid

from flask import Blueprint, render_template, request, jsonify, session

from .engine import make_puzzle, check_user_solution
from .db import Game24DB
from .i18n import get_lang, translator

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

bp = Blueprint(
    'game_24',
    __name__,
    url_prefix='/game24',
    template_folder=os.path.join(BASE_DIR, 'templates', 'game_24'),
    static_folder=os.path.join(BASE_DIR, 'static', 'game_24'),
    static_url_path='/static/game_24',
)

db = Game24DB()


def current_user():
    if 'uid' not in session:
        session['uid'] = uuid.uuid4().hex[:16]
    return session['uid']


# ---------------- 页面路由 ----------------

@bp.route('/')
def play():
    lang = get_lang(request)
    tr = translator(lang)
    return render_template('game_24/play.html', t=tr, lang=lang)


@bp.route('/history')
def history():
    lang = get_lang(request)
    tr = translator(lang)
    uid = current_user()
    attempts = db.recent_attempts(uid, limit=100)
    stats = db.accuracy(uid)
    return render_template('game_24/history.html', t=tr, lang=lang,
                           attempts=attempts, stats=stats)


# ---------------- API ----------------

@bp.route('/api/puzzle')
def api_puzzle():
    """生成一道新题（4 个数字）"""
    nums = make_puzzle(max_value=13, ensure_solvable=True)
    return jsonify({'nums': nums})


@bp.route('/api/submit', methods=['POST'])
def api_submit():
    """提交用户表达式，批改"""
    data = request.get_json() or {}
    nums = data.get('nums', [])
    expr = data.get('expr', '').strip()

    if not nums or len(nums) != 4:
        return jsonify({'error': 'invalid nums'}), 400

    correct, reason, std_answers = check_user_solution(nums, expr)

    uid = current_user()
    db.add_attempt(uid, nums, expr, correct, reason)

    return jsonify({
        'correct': correct,
        'reason': reason,
        'standard_answers': std_answers[:5],   # 最多返回 5 个参考答案
    })


@bp.route('/api/history')
def api_history():
    uid = current_user()
    after_id = int(request.args.get('after', 0))
    rows = db.recent_attempts(uid, limit=50)
    new_rows = [r for r in rows if r['id'] > after_id]
    stats = db.accuracy(uid)
    return jsonify({
        'attempts': new_rows,
        'stats': stats,
        'latest_id': rows[0]['id'] if rows else after_id,
    })