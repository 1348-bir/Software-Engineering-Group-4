# math_practice/routes.py
"""数学练习蓝图：页面、出题、批改、历史、打印与可选的图片识别。

蓝图前缀是 ``/math``，模板与静态文件都放在项目根目录的 templates/static 下，
所以这里显式指定了目录位置。练习与批改共用 ``engine`` 里的配置对象，
记录统一由 ``db``（SQLite）保存，按浏览器会话隔离。
"""
import os
import tempfile

from session_user import current_user

from flask import (Blueprint, render_template, request, jsonify, url_for)

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

# 模块级单例：蓝图导入时就完成建表，请求里直接复用。
db = MathDB()


# ---------------- 页面路由 ----------------

@bp.route('/')
def practice():
    """练习页；语言由查询参数或浏览器偏好决定。"""
    lang = get_lang(request)
    tr = translator(lang)
    return render_template('math_practice/practice.html', t=tr, lang=lang)


@bp.route('/history')
def history():
    """练习历史页：最近 100 条记录 + 正确率，仅限当前会话。"""
    lang = get_lang(request)
    tr = translator(lang)
    uid = current_user()
    attempts = db.recent_attempts(uid, limit=100)
    stats = db.accuracy(uid)
    return render_template('math_practice/history.html', t=tr, lang=lang,
                           attempts=attempts, stats=stats)


@bp.route('/upload')
def upload():
    """图片算式识别页（识别依赖可选，未安装时页面会降级提示）。"""
    lang = get_lang(request)
    tr = translator(lang)
    return render_template('math_practice/upload.html', t=tr, lang=lang)


@bp.route('/print')
def print_sheet():
    """打印卷面：按查询参数即时出题，支持练习版/答案版切换。"""
    lang = get_lang(request)
    tr = translator(lang)
    cfg = QuestionConfig.from_query(request.args)
    qs = generate_batch(cfg.count, cfg)
    questions = [{'expr': e, 'answer_text': t} for e, t, _ in qs]

    # 生成两个切换链接：一个带答案，一个不带答案，其余参数保持一致。
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
    """出题接口。

    带任一自定义参数时即时生成（不进题库，避免污染默认题库）；
    全部用默认配置时优先从题库随机取，数量不足再现场补生成。
    """
    cfg = QuestionConfig.from_query(request.args)
    custom_keys = ('num_range', 'allow_mult_div', 'allow_parentheses',
                   'allow_negative', 'allow_remainder', 'allow_fraction')
    has_custom = any(k in request.args for k in custom_keys)

    if has_custom:
        # 定制配置：即时生成，不入库。
        qs = generate_batch(cfg.count, cfg)
        return jsonify({
            'questions': [{'expr': e, 'answer': None, 'answer_text': t}
                          for e, t, _ in qs]
        })

    # 默认配置：从题库随机取题，不足时补齐。
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
    """提交批改：先做结构与长度校验，再逐题判定并写入练习记录。"""
    # 一次提交最多 200 题，请求体限制 128 KB 足够容纳。
    request.max_content_length = 128 * 1024
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('items'), list):
        return jsonify(error='提交格式错误'), 400
    if len(data['items']) > 200 or not isinstance(data.get('source', 'manual'), str) or len(data.get('source', 'manual')) > 128:
        return jsonify(error='每次最多提交 200 题'), 400
    # 逐条校验：算式与答案都必须是字符串/数字，且长度受限。
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
    """历史轮询接口：返回 ``after`` 之后的新记录与最新统计。"""
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
    """管理员接口：批量生成题库；需要 STUDIO_ADMIN_TOKEN。"""
    require_admin()
    request.max_content_length = 16 * 1024
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='参数格式错误'), 400
    count, batch = data.get('count', 100), data.get('batch', 100)
    # 注意用 type(...) is int，避免把 True/False 当成 1/0 通过校验。
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
    """图片识别接口：保存临时文件 → OCR → 与提交的答案一起批改。"""
    request.max_content_length = 8 * 1024 * 1024
    if 'image' not in request.files:
        return jsonify({'error': 'no image'}), 400
    file = request.files['image']
    request.max_content_length = 8 * 1024 * 1024
    path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            path = tmp.name
            file.save(tmp)
        expr = ocr.recognize(path)
    except RuntimeError as exc:
        return jsonify(error=str(exc), expr=''), 503
    finally:
        if path is not None:
            os.unlink(path)

    if not expr:
        # 未安装 OCR 或识别失败时返回 200 + 空表达式，前端自行降级。
        return jsonify({'error': '未识别到有效算式，请上传清晰的单道算式图片；普通文字不会作为算式批改。', 'expr': ''}), 200

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
    """如果题库为空，自动生成一批初始题目（不在每次启动时都跑）。"""
    if db.question_count() == 0:
        print(f"题库为空，开始生成 {count} 道题...")
        generate_to_db(db, count=count, batch=batch)
        print(f"完成，共 {db.question_count()} 道题")
