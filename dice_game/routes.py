# dice_game/routes.py
"""双骰游戏蓝图：页面、投掷、历史与胜率统计。

规则来自课程需求：掷两个骰子，点数总和为 7 获胜，否则失败。
蓝图前缀 ``/dice``；每次投掷都会落库，页面可轮询最新记录。
"""
import os

from session_user import current_user
from common.history import history_response

from flask import Blueprint, render_template, request, jsonify

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

# 模块级单例：导入蓝图时就建好表。
db = DiceDB()


# ---------------- 页面路由 ----------------

@bp.route('/')
def play():
    """游戏页；语言由查询参数或浏览器偏好决定。"""
    lang = get_lang(request)
    tr = translator(lang)
    return render_template('dice_game/play.html', t=tr, lang=lang)


@bp.route('/history')
def history():
    """历史页：最近 100 次投掷与胜率。"""
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
    """掷两个骰子，记录结果，返回点数、总和与是否获胜。"""
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
    """历史轮询接口：返回 ``after`` 之后的新记录与胜率统计。"""
    return history_response(db, current_user(), db.stats)
