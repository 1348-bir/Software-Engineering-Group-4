# math_practice/routes.py
import os
import tempfile
import uuid

from flask import (Blueprint, render_template, request, jsonify, session, url_for)

from .engine import QuestionConfig, generate_batch, generate_to_db, grade_batch, grade_one
from .db import MathDB
from .i18n import get_lang, translator
from . import ocr
from admin_security import require_admin

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
    return render_template('math_practice/practice.html', t=tr, lang=lang)


@bp.route('/history')
def history():
    lang = get_lang(request)
    tr = translator(lang)
    uid = current_user()
    attempts = db.recent_attempts(uid, limit=100)
    stats = db.accuracy(uid)
    return render_template('math_practice/history.html', t=tr, lang=lang,
                           attempts=attempts, stats=stats)


@bp.route('/upload')
def upload():
    lang = get_lang(request)
    tr = translator(lang)
    return render_template('math_practice/upload.html', t=tr, lang=lang)


@bp.route('/print')
def print_sheet():
    """打印卷面：按配置即时出题，支持练习版/答案版切换"""
    lang = get_lang(request)
    tr = translator(lang)
    cfg = QuestionConfig.from_query(request.args)
    qs = generate_batch(cfg.count, cfg)
    questions = [{'expr': e, 'answer_text': t} for e, t, _ in qs]

    q = cfg.to_query()
    q['show_answers'] = '1'
    toggle_answer_url = url_for('math_practice.print_sheet', **q)
    q['show_answers'] = '0'
    toggle_practice_url = url_for('math_practice.print_sheet', **q)

    return render_template('math_practice/print.html', t=tr, lang=lang,
                           questions=questions, cfg=cfg,
                           toggle_answer_url=toggle_answer_url,
                           toggle_practice_url=toggle_practice_url)


# ---------------- API ----------------

@bp.route('/api/questions')
def api_questions():
    cfg = QuestionConfig.from_query(request.args)
    custom_keys = ('num_range', 'allow_mult_div', 'allow_parentheses',
                   'allow_negative', 'allow_remainder', 'allow_fraction')
    has_custom = any(k in request.args for k in custom_keys)

    if has_custom:
        # 定制配置：即时生成，不入库（避免污染题库）
        qs = generate_batch(cfg.count, cfg)
        return jsonify({
            'questions': [{'expr': e, 'answer': None, 'answer_text': t}
                          for e, t, _ in qs]
        })

    # 默认配置：从题库随机取题，不足时补齐
    n = cfg.count
    qs = db.random_questions(n)
    if len(qs) < n:
        extra = generate_batch(n - len(qs))
        for e, t, a in extra:
            qs.append((e, int(a)))
    return jsonify({
        'questions': [{'expr': e, 'answer': a, 'answer_text': str(a)}
                      for e, a in qs]
    })


@bp.route('/api/submit', methods=['POST'])
def api_submit():
    request.max_content_length = 128 * 1024
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('items'), list):
        return jsonify(error='提交格式错误'), 400
    if len(data['items']) > 200 or not isinstance(data.get('source', 'manual'), str) or len(data.get('source', 'manual')) > 128:
        return jsonify(error='每次最多提交 200 题'), 400
    for item in data['items']:
        if (not isinstance(item, dict) or not isinstance(item.get('expr'), str)
                or len(item['expr']) > 512 or not isinstance(item.get('answer'), (str, int, float))
                or len(str(item['answer'])) > 128):
            return jsonify(error='算式或答案格式错误、长度超限'), 400
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
    require_admin()
    request.max_content_length = 16 * 1024
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='参数格式错误'), 400
    count, batch = data.get('count', 100), data.get('batch', 100)
    if type(count) is not int or not 1 <= count <= 1000 or type(batch) is not int or not 1 <= batch <= 200:
        return jsonify(error='题数必须为 1 到 1000，批次大小必须为 1 到 200'), 400
    try:
        cfg = QuestionConfig.from_dict(data)
    except (ValueError, TypeError, OverflowError):
        return jsonify(error='出题配置错误'), 400
    total = generate_to_db(db, count=count, batch=batch, cfg=cfg)
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

def init_question_bank(count=1000, batch=200):
    """如果题库为空，自动生成"""
    if db.question_count() == 0:
        print(f"题库为空，开始生成 {count} 道题...")
        generate_to_db(db, count=count, batch=batch)
        print(f"完成，共 {db.question_count()} 道题")
