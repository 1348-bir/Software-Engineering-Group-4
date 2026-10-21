from flask import Flask, render_template, request, session, g, redirect, url_for
import random
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from safe_math import evaluate

app = Flask(__name__)
DATABASE = str(Path(__file__).resolve().parent / 'history.db')

# ==================== 多语言配置 ====================
TRANSLATIONS = {
    'zh': {
        'title': '趣味数学乐园', 'choose_module': '请选择模块', 'arithmetic': '算术练习',
        'game24': '24点游戏', 'submit': '提交答案', 'back_home': '返回首页',
        'score': '得分', 'accuracy': '准确率', 'time_taken': '用时', 'history': '历史记录',
        'seconds': '秒', 'history_title': '历史成绩记录', 'module': '模块', 'date': '时间',
        'no_history': '暂无历史记录', 'try_again': '再做一次', 'correct': '回答正确',
        'wrong': '回答错误', 'your_answer': '你的答案', 'correct_answer': '正确答案',
        'expression': '原题目'
    },
    'en': {
        'title': 'Math Fun Park', 'choose_module': 'Choose Module', 'arithmetic': 'Arithmetic Practice',
        'game24': '24 Game', 'submit': 'Submit', 'back_home': 'Back to Home',
        'score': 'Score', 'accuracy': 'Accuracy', 'time_taken': 'Time', 'history': 'History',
        'seconds': 's', 'history_title': 'History Records', 'module': 'Module', 'date': 'Date',
        'no_history': 'No history records yet', 'try_again': 'Try Again', 'correct': 'Correct',
        'wrong': 'Wrong', 'your_answer': 'Your Answer', 'correct_answer': 'Correct Answer',
        'expression': 'Expression'
    }
}


@app.before_request
def before_request():
    lang = request.args.get('lang')
    if lang in TRANSLATIONS:
        session['lang'] = lang
    elif 'lang' not in session:
        session['lang'] = 'zh'
    g.lang = session['lang']
    g.t = TRANSLATIONS[g.lang]


@app.context_processor
def inject_translations():
    return dict(t=g.t, current_lang=g.lang)


# ==================== 数据库初始化 ====================
def init_db():
    with app.app_context():
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS history
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      module TEXT, score INTEGER, accuracy REAL,
                      time_taken REAL, timestamp TEXT)''')
        conn.commit()
        conn.close()


def add_history(module, score, accuracy, time_taken):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO history (module, score, accuracy, time_taken, timestamp) VALUES (?, ?, ?, ?, ?)",
              (module, score, accuracy, time_taken, timestamp))
    conn.commit()
    conn.close()


def get_history():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT module, score, accuracy, time_taken, timestamp FROM history ORDER BY id DESC LIMIT 20")
    rows = c.fetchall()
    conn.close()
    return rows


# ==================== 算术练习逻辑 ====================
def generate_questions(num=10):
    questions = []
    operators = ['+', '-', '*', '/']
    for _ in range(num):
        while True:
            op1, op2 = random.choice(operators), random.choice(operators)
            num1, num2, num3 = random.randint(1, 99), random.randint(1, 99), random.randint(1, 99)
            if (op1 == '/' and num2 == 0) or (op2 == '/' and num3 == 0): continue
            expression = f"{num1} {op1} {num2} {op2} {num3}"
            try:
                answer = evaluate(expression)
                if 0 <= answer <= 100 and answer == int(answer):
                    questions.append({'expression': expression, 'answer': int(answer)})
                    break
            except ZeroDivisionError:
                continue
    return questions


@app.route('/arithmetic')
def arithmetic():
    questions_data = generate_questions(10)
    session['exam_data'] = questions_data
    session['start_time'] = time.time()
    frontend_questions = [{'expression': q['expression']} for q in questions_data]
    return render_template('arithmetic.html', questions=frontend_questions)


@app.route('/arithmetic/submit', methods=['POST'])
def arithmetic_submit():
    exam_data = session.pop('exam_data', [])
    if not exam_data:
        return redirect(url_for('arithmetic'))
    start_time = session.get('start_time', time.time())
    time_taken = round(time.time() - start_time, 2)

    user_answers = [request.form.get(f'answer_{i}', '').strip() for i in range(len(exam_data))]
    score, results = 0, []

    for i, q_data in enumerate(exam_data):
        correct = q_data['answer']
        expression = q_data['expression']
        user_ans = user_answers[i]
        is_correct = user_ans.isdigit() and int(user_ans) == correct
        if is_correct: score += 10
        results.append({
            'index': i + 1, 'expression': expression,
            'user_answer': user_ans if user_ans else '未作答',
            'correct_answer': correct, 'is_correct': is_correct
        })

    accuracy = round((score / 100) * 100, 2)
    add_history('算术练习', score, accuracy, time_taken)

    return render_template('result.html', score=score, accuracy=accuracy, time_taken=time_taken, results=results)


# ==================== 24点游戏逻辑 ====================
def solve_24(nums):
    """
    递归求解24点，返回 (是否可解, 表达式字符串)
    nums 格式为 [(数值, 表达式字符串), ...]
    """
    if len(nums) == 1:
        if abs(nums[0][0] - 24) < 1e-6:
            expr = nums[0][1]
            if expr.startswith('(') and expr.endswith(')'):
                expr = expr[1:-1]
            return True, expr
        return False, ""

    for i in range(len(nums)):
        for j in range(len(nums)):
            if i != j:
                new_nums = [nums[k] for k in range(len(nums)) if k != i and k != j]
                a, expr_a = nums[i]
                b, expr_b = nums[j]

                operations = [
                    (a + b, f"({expr_a} + {expr_b})"),
                    (a - b, f"({expr_a} - {expr_b})"),
                    (b - a, f"({expr_b} - {expr_a})"),
                    (a * b, f"({expr_a} * {expr_b})"),
                ]
                if abs(b) > 1e-6: operations.append((a / b, f"({expr_a} / {expr_b})"))
                if abs(a) > 1e-6: operations.append((b / a, f"({expr_b} / {expr_a})"))

                for res, expr in operations:
                    found, final_expr = solve_24(new_nums + [(res, expr)])
                    if found:
                        return True, final_expr
    return False, ""


def generate_24_nums():
    """生成一组一定有解的4个数字"""
    while True:
        nums = [random.randint(1, 13) for _ in range(4)]
        num_tuples = [(n, str(n)) for n in nums]
        solvable, _ = solve_24(num_tuples)
        if solvable:
            return nums


@app.route('/game24')
def game24():
    nums = generate_24_nums()
    session['game24_finished'] = False
    session['game24_nums'] = nums
    session['game24_start_time'] = time.time()
    return render_template('game24.html', nums=nums, message=None, is_correct=None, show_solution=False)


@app.route('/game24/check', methods=['POST'])
def game24_check():
    nums = session.get('game24_nums', [])
    if not nums:
        return redirect(url_for('game24'))
    expression = request.form.get('expression', '').strip()
    start_time = session.get('game24_start_time', time.time())

    if not expression:
        return render_template('game24.html', nums=nums, message="请输入你的算式！", is_correct=False,
                               show_solution=False)
    if not re.match(r'^[\d\+\-\*/\(\)\s]+$', expression):
        return render_template('game24.html', nums=nums, message="算式包含非法字符！", is_correct=False,
                               show_solution=False)

    nums_in_expr = list(map(int, re.findall(r'\d+', expression)))
    if sorted(nums_in_expr) != sorted(nums):
        return render_template('game24.html', nums=nums, message="必须且只能使用给定的4个数字，每个数字只能用一次！",
                               is_correct=False, show_solution=False)

    try:
        result = evaluate(expression)
        if abs(result - 24) < 1e-6:
            time_taken = round(time.time() - start_time, 2)
            if not session.get('game24_finished', False):
                add_history('24点游戏', 100, 100.0, time_taken)
            session['game24_finished'] = True
            return render_template('game24.html', nums=nums, message="🎉 恭喜你，答案正确！", is_correct=True,
                                   show_solution=False)
        else:
            return render_template('game24.html', nums=nums, message=f"结果等于 {result:.2f}，不等于 24。再试一次吧！",
                                   is_correct=False, show_solution=False)
    except ZeroDivisionError:
        return render_template('game24.html', nums=nums, message="除数不能为0！", is_correct=False, show_solution=False)
    except Exception:
        return render_template('game24.html', nums=nums, message="算式语法错误，请检查括号和运算符。", is_correct=False,
                               show_solution=False)


@app.route('/game24/solution')
def game24_solution():
    """查看当前题目的正确答案"""
    nums = session.get('game24_nums', [])
    session['game24_finished'] = True
    if not nums:
        return redirect(url_for('game24'))

    num_tuples = [(n, str(n)) for n in nums]
    solvable, solution_expr = solve_24(num_tuples)

    if solvable:
        message = f"💡 参考答案：{solution_expr} = 24 （查看答案不计入成绩）"
    else:
        message = "抱歉，此题无解。"

    return render_template('game24.html', nums=nums, message=message, is_correct=True, show_solution=True)


# ==================== 首页与历史记录 ====================
@app.route('/')
def home():
    return render_template('home.html')


@app.route('/history')
def history():
    records = get_history()
    return render_template('history.html', records=records)


if __name__ == '__main__':
    raise SystemExit('请运行 app.py 启动完整项目。')
