# math_practice/routes.py
import os
import tempfile
import uuid

from flask import (Blueprint, render_template, request, jsonify, session)

from .engine import generate_batch, generate_to_db, grade_batch, grade_one
from .db import MathDB
from .i18n import get_lang, translator
from . import ocr

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

bp = Blueprint(
    'math_practice',
    __name__,
    url_prefix='/math',
    template_folder=os.path.join(BASE_DIR, 'templates', 'math_practice'),
    static_folder=os.path.join(BASE_DIR, 'static', 'math_practice'),
    static_url_path='/static/math_practice',
)

db = MathDB()


def current_user():
    if 'uid' not in session:
        session['uid'] = uuid.uuid4().hex[:16]
    return session['uid']


# ---------------- 页面路由 ----------------

@bp.route('/')
def practice():
    lang = get_lang(request)
    tr = translator(lang)
    return render_template('practice.html', t=tr, lang=lang)


@bp.route('/history')
def history():
    lang = get_lang(request)
    tr = translator(lang)
    uid = current_user()
    attempts = db.recent_attempts(uid, limit=100)
    stats = db.accuracy(uid)
    return render_template('history.html', t=tr, lang=lang,
                           attempts=attempts, stats=stats)


@bp.route('/upload')
def upload():
    lang = get_lang(request)
    tr = translator(lang)
    return render_template('upload.html', t=tr, lang=lang)


# ---------------- API ----------------

@bp.route('/api/questions')
def api_questions():
    n = int(request.args.get('n', 10))
    qs = db.random_questions(n)
    if len(qs) < n:
        extra = generate_batch(n - len(qs))
        qs.extend(extra)
    return jsonify({
        'questions': [{'expr': e, 'answer': a} for e, a in qs]
    })


@bp.route('/api/submit', methods=['POST'])
def api_submit():
    data = request.get_json()
    items = [(it['expr'], it['answer']) for it in data.get('items', [])]
    results = grade_batch(items)
    uid = current_user()

    for r in results:
        db.add_attempt(
            user_id=uid,
            expr=r['expr'],
            user_answer=r['user_answer'],
            standard=r['standard'],
            is_correct=r['correct'],
            source=data.get('source', 'manual'),
        )

    correct = sum(1 for r in results if r['correct'])
    total = len(results)
    return jsonify({
        'results': results,
        'total': total,
        'correct': correct,
        'accuracy': (correct / total) if total else 0.0,
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


@bp.route('/api/generate', methods=['POST'])
def api_generate():
    data = request.get_json() or {}
    count = int(data.get('count', 10000))
    batch = int(data.get('batch', 500))
    total = generate_to_db(db, count=count, batch=batch)
    return jsonify({'generated': total, 'total_in_db': db.question_count()})


@bp.route('/api/ocr', methods=['POST'])
def api_ocr():
    if 'image' not in request.files:
        return jsonify({'error': 'no image'}), 400
    file = request.files['image']
    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
        file.save(tmp.name)
        expr = ocr.recognize(tmp.name)
    os.unlink(tmp.name)

    if not expr:
        return jsonify({'error': 'ocr failed or not installed', 'expr': ''}), 200

    user_answer = request.form.get('answer', '')
    ok, std, uv = grade_one(expr, user_answer)

    uid = current_user()
    db.add_attempt(uid, expr, user_answer, std, ok, source='ocr')

    return jsonify({
        'expr': expr,
        'correct': ok,
        'standard': std,
    })


# ---------------- 启动时初始化题库 ----------------

def init_question_bank(count=10000, batch=500):
    """如果题库为空，自动生成"""
    if db.question_count() == 0:
        print(f"题库为空，开始生成 {count} 道题...")
        generate_to_db(db, count=count, batch=batch)
        print(f"完成，共 {db.question_count()} 道题")