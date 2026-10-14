# math_practice/engine.py
"""
逆波兰表达式引擎 + 调度场算法 + 题库生成 + 批改。
支持运算符: + - × ÷ ^ ( ) 以及一元负号 u-
"""

import random

PRECEDENCE = {
    '+': 1, '-': 1,
    '×': 2, '÷': 2,
    '^': 3,
    'u-': 4,
}

RIGHT_ASSOC = {'^', 'u-'}

OPS = ['+', '-', '×', '÷']


# ---------------- 调度场算法 ----------------

def tokenize(expr):
    tokens = []
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit():
            num = ''
            while i < len(expr) and expr[i].isdigit():
                num += expr[i]
                i += 1
            tokens.append(num)
            continue
        if ch in '+-×÷^()':
            tokens.append(ch)
            i += 1
            continue
        raise ValueError(f"非法字符: {ch}")
    return tokens


def to_rpn(tokens):
    """调度场算法：中缀 token -> 逆波兰 token"""
    output = []
    stack = []
    prev = None

    for tok in tokens:
        if tok.isdigit():
            output.append(tok)
        elif tok == '(':
            stack.append(tok)
        elif tok == ')':
            while stack and stack[-1] != '(':
                output.append(stack.pop())
            if not stack:
                raise ValueError("括号不匹配")
            stack.pop()
        else:
            if tok == '-' and (prev is None or prev in '+-×÷^('):
                tok = 'u-'
            while (stack and stack[-1] != '('
                   and (PRECEDENCE[stack[-1]] > PRECEDENCE[tok]
                        or (PRECEDENCE[stack[-1]] == PRECEDENCE[tok]
                            and tok not in RIGHT_ASSOC))):
                output.append(stack.pop())
            stack.append(tok)
        prev = tok

    while stack:
        if stack[-1] == '(':
            raise ValueError("括号不匹配")
        output.append(stack.pop())

    return output


def eval_rpn(rpn):
    """求逆波兰表达式的值"""
    stack = []
    for tok in rpn:
        if tok.isdigit():
            stack.append(int(tok))
        elif tok == 'u-':
            a = stack.pop()
            stack.append(-a)
        else:
            b = stack.pop()
            a = stack.pop()
            if tok == '+':
                stack.append(a + b)
            elif tok == '-':
                stack.append(a - b)
            elif tok == '×':
                stack.append(a * b)
            elif tok == '÷':
                if b == 0:
                    raise ZeroDivisionError
                stack.append(a / b)
            elif tok == '^':
                stack.append(a ** b)
    if len(stack) != 1:
        raise ValueError("表达式非法")
    return stack[0]


def evaluate(expr):
    """
    中缀表达式 -> (是否合法, 结果整数)。
    分步校验：每一步都必须是 0~100 的整数。
    """
    try:
        rpn = to_rpn(tokenize(expr))
    except Exception:
        return False, None

    stack = []
    for tok in rpn:
        if tok.isdigit():
            v = int(tok)
            if v < 0 or v > 100:
                return False, None
            stack.append(v)
        elif tok == 'u-':
            a = stack.pop()
            v = -a
            if v < 0 or v > 100:
                return False, None
            stack.append(v)
        else:
            if len(stack) < 2:
                return False, None
            b = stack.pop()
            a = stack.pop()
            if tok == '+':
                v = a + b
            elif tok == '-':
                v = a - b
            elif tok == '×':
                v = a * b
            elif tok == '÷':
                if b == 0 or a % b != 0:
                    return False, None
                v = a // b
            elif tok == '^':
                v = a ** b
                if v > 100:
                    return False, None
            else:
                return False, None

            if v < 0 or v > 100:
                return False, None
            stack.append(v)

    if len(stack) != 1:
        return False, None

    result = stack[0]
    if not isinstance(result, int):
        return False, None
    return True, result


# ---------------- 题库生成 ----------------

def make_expr(max_value=100):
    a = random.randint(0, max_value)
    b = random.randint(0, max_value)
    c = random.randint(0, max_value)
    op1 = random.choice(OPS)
    op2 = random.choice(OPS)
    return f"{a} {op1} {b} {op2} {c}"


def generate_batch(count, max_value=100, seed=None, max_zero=5):
    """
    生成 count 道不重复且合法的题。
    返回 [(expr, answer), ...]
    max_zero: 整个批次里数字 0 最多出现的次数
    """
    if seed is not None:
        random.seed(seed)

    result = []
    seen = set()
    zero_used = 0
    guard = 0
    limit = count * 500

    while len(result) < count and guard < limit:
        guard += 1
        expr = make_expr(max_value=max_value)
        if expr in seen:
            continue

        ok, ans = evaluate(expr)
        if not ok:
            continue

        parts = expr.split()
        zeros_here = sum(1 for p in parts if p == '0')
        if zero_used + zeros_here > max_zero:
            continue

        seen.add(expr)
        result.append((expr, ans))
        zero_used += zeros_here

    return result


def generate_to_db(db, count=10000, batch=500, max_value=100, seed=None):
    """分批生成并写入数据库，避免一次性占内存"""
    total = 0
    while total < count:
        n = min(batch, count - total)
        qs = generate_batch(n, max_value=max_value, seed=seed)
        for expr, ans in qs:
            db.add_question(expr, ans)
            total += 1
        print(f"已生成 {total}/{count}")
    return total


# ---------------- 批改 ----------------

def grade_one(expr, user_answer):
    """批改单题。返回 (是否正确, 标准答案, 用户答案)"""
    ok, std = evaluate(expr)
    if not ok:
        return False, None, user_answer

    try:
        user_val = int(str(user_answer).strip())
    except (ValueError, TypeError):
        return False, std, user_answer

    return user_val == std, std, user_val


def grade_batch(items):
    """批量批改。items = [(expr, user_answer), ...]"""
    results = []
    for expr, ua in items:
        correct, std, uv = grade_one(expr, ua)
        results.append({
            'expr': expr,
            'user_answer': ua,
            'correct': correct,
            'standard': std,
        })
    return results