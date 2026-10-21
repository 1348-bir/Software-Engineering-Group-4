# math_practice/engine.py
"""
逆波兰表达式引擎 + 调度场算法 + 可定制出题 + 批改。
支持运算符: + - × ÷ ^ ( ) 以及一元负号 u-

配置驱动：QuestionConfig 集中所有定制项（乘除、括号、负数、
除法余数、分数、数值范围、打印参数），表达式生成-校验-批改
全部走配置，默认配置行为与旧版一致。
"""

import random
import re
from dataclasses import dataclass
from fractions import Fraction

PRECEDENCE = {
    '+': 1, '-': 1,
    '×': 2, '÷': 2,
    '^': 3,
    'u-': 4,
}

RIGHT_ASSOC = {'^', 'u-'}

OPS = ['+', '-', '×', '÷']

_TOKEN_NUM = re.compile(r'^\d+(/\d+)?$')


def _as_bool(v):
    """宽松解析布尔值：支持 0/1、true/false、yes/no 字符串"""
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return bool(v)
    return str(v).strip().lower() in ('1', 'true', 'yes', 'on')


@dataclass
class QuestionConfig:
    """出题配置。所有定制项集中在此，便于扩展。"""
    count: int = 10                  # 题目数量
    num_range: int = 20              # 运算数绝对值上限
    allow_mult_div: bool = False     # 是否含 × ÷
    allow_parentheses: bool = False  # 是否含括号
    allow_negative: bool = False     # 题面/中间步骤可否为负（答案仍限 answer_range）
    allow_remainder: bool = False    # 除法是否允许余数
    allow_fraction: bool = False     # 数字可为分数 + 结果可用分数表示
    answer_range: tuple = (0, 100)   # 最终答案范围
    # ---- 打印参数（供 /math/print 使用）----
    columns: int = 2                 # 每行题数
    show_answers: bool = False       # 答案版
    line_spacing: float = 1.0        # 行距倍率

    def to_dict(self):
        return {
            'count': self.count,
            'num_range': self.num_range,
            'allow_mult_div': self.allow_mult_div,
            'allow_parentheses': self.allow_parentheses,
            'allow_negative': self.allow_negative,
            'allow_remainder': self.allow_remainder,
            'allow_fraction': self.allow_fraction,
            'columns': self.columns,
            'show_answers': self.show_answers,
            'line_spacing': self.line_spacing,
        }

    @classmethod
    def from_dict(cls, d):
        cfg = cls()
        cfg.count = max(1, min(int(d.get('count', d.get('n', cfg.count))), 200))
        cfg.num_range = max(1, int(d.get('num_range', cfg.num_range)))
        cfg.allow_mult_div = _as_bool(d.get('allow_mult_div', cfg.allow_mult_div))
        cfg.allow_parentheses = _as_bool(d.get('allow_parentheses', cfg.allow_parentheses))
        cfg.allow_negative = _as_bool(d.get('allow_negative', cfg.allow_negative))
        cfg.allow_remainder = _as_bool(d.get('allow_remainder', cfg.allow_remainder))
        cfg.allow_fraction = _as_bool(d.get('allow_fraction', cfg.allow_fraction))
        cfg.columns = max(1, min(int(d.get('columns', cfg.columns)), 4))
        cfg.show_answers = _as_bool(d.get('show_answers', cfg.show_answers))
        cfg.line_spacing = max(0.5, min(float(d.get('line_spacing', cfg.line_spacing)), 3.0))
        return cfg

    @classmethod
    def from_query(cls, args):
        """args: MultiDict 或 dict（query 参数均为字符串）"""
        return cls.from_dict(args)

    def to_query(self):
        d = self.to_dict()
        return {k: str(v) for k, v in d.items()}


# ---------------- 表达式层（支持分数 token） ----------------

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
            # 分数：数字 紧跟 '/数字'
            if (i < len(expr) and expr[i] == '/'
                    and i + 1 < len(expr) and expr[i + 1].isdigit()):
                num += '/'
                i += 1
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


def _is_num(tok):
    return bool(_TOKEN_NUM.match(tok))


def _parse_num(tok):
    if '/' in tok:
        n, d = tok.split('/', 1)
        return Fraction(int(n), int(d))
    return Fraction(int(tok))


def to_rpn(tokens):
    """调度场算法：中缀 token -> 逆波兰 token"""
    output = []
    stack = []
    prev = None

    for tok in tokens:
        if _is_num(tok):
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
    """求逆波兰表达式的值（Fraction 精确运算）"""
    stack = []
    for tok in rpn:
        if _is_num(tok):
            stack.append(_parse_num(tok))
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


def solve(expr):
    """纯求值（Fraction），不校验范围。返回 (是否合法, Fraction)"""
    try:
        rpn = to_rpn(tokenize(expr))
        val = eval_rpn(rpn)
    except Exception:
        return False, None
    return True, val


def evaluate(expr, cfg=None):
    """按配置校验表达式。返回 (是否合法, Fraction 答案)"""
    cfg = cfg or QuestionConfig()
    lo, hi = cfg.answer_range
    try:
        rpn = to_rpn(tokenize(expr))
    except Exception:
        return False, None

    # 题面负数：u- 出现在 rpn 中即代表表达式含负号
    if not cfg.allow_negative and 'u-' in rpn:
        return False, None

    stack = []
    for tok in rpn:
        if _is_num(tok):
            v = _parse_num(tok)
            if abs(v) > cfg.num_range:
                return False, None
            stack.append(v)
        elif tok == 'u-':
            a = stack.pop()
            stack.append(-a)
        else:
            if len(stack) < 2:
                return False, None
            b = stack.pop()
            a = stack.pop()
            if tok == '÷':
                if b == 0:
                    return False, None
                # 无余数且无分数 -> 必须整除
                if not cfg.allow_remainder and not cfg.allow_fraction:
                    if a.denominator != 1 or b.denominator != 1:
                        return False, None
                    if a % b != 0:
                        return False, None
                v = a / b
            elif tok == '+':
                v = a + b
            elif tok == '-':
                v = a - b
            elif tok == '×':
                v = a * b
            elif tok == '^':
                if b.denominator != 1 or b < 0:
                    return False, None
                v = a ** int(b)
            else:
                return False, None
            if not cfg.allow_negative and v < 0:
                return False, None
            stack.append(v)

    if len(stack) != 1:
        return False, None

    v = stack[0]
    if v < lo or v > hi:
        return False, None
    if not cfg.allow_fraction and not cfg.allow_remainder and v.denominator != 1:
        return False, None
    return True, v


# ---------------- 可定制出题 ----------------

def format_answer(value, allow_fraction=False):
    """Fraction -> 显示文本：整数 / 分数 / 小数"""
    if value.denominator == 1:
        return str(int(value.numerator))
    if allow_fraction:
        return f"{value.numerator}/{value.denominator}"
    dec = float(value)
    return f"{dec:.2f}".rstrip('0').rstrip('.')


def _gen_ops(cfg):
    ops = ['+', '-']
    if cfg.allow_mult_div:
        ops += ['×', '÷']
    return ops


def _gen_number(cfg, integral_only=False):
    """生成一个运算数 token，可为负数 / 分数"""
    if integral_only or not cfg.allow_fraction:
        tok = str(random.randint(0, cfg.num_range))
    else:
        if random.random() < 0.35:
            d = random.randint(2, 9)
            n = random.randint(1, cfg.num_range)
            tok = f"{n}/{d}"
        else:
            tok = str(random.randint(0, cfg.num_range))
    if cfg.allow_negative and random.random() < 0.35:
        tok = '-' + tok
    return tok


def _build_expr(a, op1, b, op2, c, paren):
    if paren:
        if random.random() < 0.5:
            return f"({a} {op1} {b}) {op2} {c}"
        return f"{a} {op1} ({b} {op2} {c})"
    return f"{a} {op1} {b} {op2} {c}"


def make_expr(cfg):
    """按配置生成一道表达式（合法性交给 generate_batch 里的 evaluate 过滤）"""
    ops = _gen_ops(cfg)
    for _ in range(30):
        need_div_int = not cfg.allow_remainder and not cfg.allow_fraction
        op1 = random.choice(ops)
        op2 = random.choice(ops)

        if op1 == '÷' and need_div_int:
            # 保证 a ÷ b 整除：b 取 1..num_range，a 取 b 的倍数
            b = str(random.randint(1, cfg.num_range))
            bv = int(b)
            a_val = bv * random.randint(0, cfg.num_range // bv)
            a = ('-' if (cfg.allow_negative and random.random() < 0.35) else '') + str(a_val)
        else:
            a = _gen_number(cfg)
            b = _gen_number(cfg)
        c = _gen_number(cfg)

        expr = _build_expr(a, op1, b, op2, c, cfg.allow_parentheses)
        if not cfg.allow_parentheses:
            return expr

        # 括号有效性：去掉外层括号后若求值相同，说明括号冗余 -> 重试
        plain = f"{a} {op1} {b} {op2} {c}"
        ok1, v1 = solve(expr)
        ok2, v2 = solve(plain)
        if ok1 and ok2 and v1 != v2:
            return expr

    # 兜底：放弃括号
    a = _gen_number(cfg)
    b = _gen_number(cfg)
    c = _gen_number(cfg)
    return f"{a} {op1} {b} {op2} {c}"


def generate_batch(count, cfg=None, seed=None, max_zero=5):
    """
    生成 count 道不重复且合法的题。
    返回 [(expr, answer_text, answer_Fraction), ...]
    max_zero: 整个批次里数字 0 最多出现的次数
    """
    if seed is not None:
        random.seed(seed)
    cfg = cfg or QuestionConfig()

    result = []
    seen = set()
    zero_used = 0
    guard = 0
    limit = max(1000, count * 500)

    while len(result) < count and guard < limit:
        guard += 1
        expr = make_expr(cfg)
        if expr in seen:
            continue

        ok, ans = evaluate(expr, cfg)
        if not ok:
            continue

        parts = expr.split()
        zeros_here = sum(1 for p in parts if p == '0' or p.startswith('0/'))
        if zero_used + zeros_here > max_zero:
            continue

        seen.add(expr)
        result.append((expr, format_answer(ans, cfg.allow_fraction), ans))
        zero_used += zeros_here

    return result


def generate_to_db(db, count=10000, batch=500, cfg=None, seed=None):
    """分批生成并写入数据库，避免一次性占内存。仅入库整数且答案在 0-100 的题。"""
    total = 0
    guard = 0
    cfg = cfg or QuestionConfig(num_range=100)
    while total < count and guard < count * 100:
        guard += 1
        n = min(batch, count - total)
        qs = generate_batch(n, cfg=cfg, seed=seed)
        for expr, ans_text, ans in qs:
            if ans.denominator != 1:
                continue
            v = int(ans.numerator)
            if v < 0 or v > 100:
                continue
            db.add_question(expr, v)
            total += 1
        print(f"已生成 {total}/{count}")
    return total


# ---------------- 批改 ----------------

def parse_user_answer(text):
    """把用户输入解析为 Fraction；支持 整数 / 小数 / 分数 / 带分数。解析失败返回 None。"""
    s = str(text).strip()
    if not s:
        return None
    if ' ' in s:
        parts = s.split()
        if len(parts) == 2 and '/' in parts[1]:
            try:
                whole = int(parts[0])
                frac = Fraction(parts[1])
                return whole + frac
            except (ValueError, ZeroDivisionError):
                return None
    try:
        return Fraction(s)
    except (ValueError, ZeroDivisionError):
        return None


def grade_one(expr, user_answer):
    """批改单题。返回 (是否正确, 标准答案文本, 用户答案)"""
    ok, std = solve(expr)
    if not ok:
        return False, None, user_answer

    std_text = format_answer(std, allow_fraction=True)
    uv = parse_user_answer(user_answer)
    if uv is None:
        return False, std_text, user_answer
    return uv == std, std_text, user_answer


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
