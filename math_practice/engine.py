# math_practice/engine.py
"""
逆波兰表达式引擎 + 调度场算法 + 可定制出题 + 批改。

支持运算符：+ - × ÷ ^ ( ) 以及一元负号 u-。
配置驱动：QuestionConfig 集中所有定制项（乘除、括号、负数、除法余数、
分数、数值范围、打印参数），出题、校验、批改全部走同一份配置。

为什么用逆波兰 + Fraction：
- 逆波兰不需要递归求值，括号和优先级在转换阶段就处理掉了；
- Fraction 用分数精确表示，1/3 这类中间结果不会出现浮点误差。
"""

import random
import re
import time
from dataclasses import dataclass
from fractions import Fraction

from common.arithmetic import (
    MAX_EXPRESSION, MAX_NUMBER_DIGITS, MAX_VALUE_BITS, MAX_EXPONENT,
    PRECEDENCE, RIGHT_ASSOC, OPS, bounded_value, bounded_power,
    tokenize, to_rpn, eval_rpn, solve,
)


def _as_bool(v):
    """宽松解析布尔值：支持 0/1、true/false、yes/no 字符串。"""
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
        """导出为普通字典，供模板与调试使用（不含 answer_range）。"""
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
        """从字典构造配置，并把每一项限制在允许范围内（防止恶意超大参数）。"""
        cfg = cls()
        cfg.count = max(1, min(int(d.get('count', d.get('n', cfg.count))), 200))
        cfg.num_range = max(1, min(int(d.get('num_range', cfg.num_range)), 1000))
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
        """从查询参数构造配置（args 是 MultiDict 或 dict，值都是字符串）。"""
        return cls.from_dict(args)

    def to_query(self):
        """导出为查询串字典，所有值转成字符串，便于拼 URL。"""
        d = self.to_dict()
        return {k: str(v) for k, v in d.items()}


# ---------------- 表达式层（支持分数 token） ----------------

def evaluate(expr, cfg=None):
    """Apply practice policy using the shared parser and arithmetic interpreter."""
    try:
        return True, eval_rpn(to_rpn(tokenize(expr)), cfg or QuestionConfig())
    except (ValueError, ZeroDivisionError, IndexError, KeyError, TypeError):
        return False, None


# ---------------- 可定制出题 ----------------

def format_answer(value, allow_fraction=False):
    """把 Fraction 转成展示文本：整数、分数或保留两位的小数。"""
    if value.denominator == 1:
        return str(int(value.numerator))
    if allow_fraction:
        return f"{value.numerator}/{value.denominator}"
    dec = float(value)
    return f"{dec:.2f}".rstrip('0').rstrip('.')


def _gen_ops(cfg):
    """按配置返回可用的运算符集合。"""
    ops = ['+', '-']
    if cfg.allow_mult_div:
        ops += ['×', '÷']
    return ops


def _gen_number(cfg, integral_only=False):
    """生成一个运算数 token；按配置可出现分数或负号。"""
    if integral_only or not cfg.allow_fraction:
        tok = str(random.randint(0, cfg.num_range))
    else:
        # 约三分之一概率生成真分数，其余为整数。
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
    """按「三数两运算符」拼算式；开括号时随机选择加括号的位置。"""
    if paren:
        if random.random() < 0.5:
            return f"({a} {op1} {b}) {op2} {c}"
        return f"{a} {op1} ({b} {op2} {c})"
    return f"{a} {op1} {b} {op2} {c}"


def make_expr(cfg):
    """按配置生成一条候选算式；合法性交给 generate_batch 里的 evaluate 过滤。"""
    ops = _gen_ops(cfg)
    for _ in range(30):
        need_div_int = not cfg.allow_remainder and not cfg.allow_fraction
        op1 = random.choice(ops)
        op2 = random.choice(ops)

        if op1 == '÷' and need_div_int:
            # 要求整除时先造除数，再取它的倍数当被除数，保证除得尽。
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

        # 括号有效性：去掉括号后若求值相同，说明括号是冗余的，重试。
        plain = f"{a} {op1} {b} {op2} {c}"
        ok1, v1 = solve(expr)
        ok2, v2 = solve(plain)
        if ok1 and ok2 and v1 != v2:
            return expr

    # 兜底：放弃括号，直接返回一条普通算式。
    a = _gen_number(cfg)
    b = _gen_number(cfg)
    c = _gen_number(cfg)
    return f"{a} {op1} {b} {op2} {c}"


def generate_batch(count, cfg=None, seed=None, max_zero=5, deadline=None):
    """
    生成 count 道不重复且合法的题。
    返回 [(expr, answer_text, answer_Fraction), ...]。

    max_zero：整个批次里数字 0 最多出现几次（避免题目全是 0）；
    deadline：时间预算，到点就停，返回已生成的题。
    """
    if seed is not None:
        random.seed(seed)
    cfg = cfg or QuestionConfig()
    # 普通练习与打印也走时间预算，避免苛刻配置下长时间无响应。
    if deadline is None:
        deadline = time.monotonic() + 2

    result = []
    seen = set()
    zero_used = 0
    guard = 0
    limit = max(1000, count * 500)      # 生成尝试次数上限，防止死循环

    while len(result) < count and guard < limit:
        if time.monotonic() >= deadline:
            break
        guard += 1
        expr = make_expr(cfg)
        if expr in seen:
            continue

        ok, ans = evaluate(expr, cfg)
        if not ok:
            continue

        # 统计本条算式里 0 的个数，超过配额就丢弃。
        parts = expr.split()
        zeros_here = sum(1 for p in parts if p == '0' or p.startswith('0/'))
        if zero_used + zeros_here > max_zero:
            continue

        seen.add(expr)
        result.append((expr, format_answer(ans, cfg.allow_fraction), ans))
        zero_used += zeros_here

    return result


def generate_to_db(db, count=100, batch=100, cfg=None, seed=None):
    """分批生成并写入题库，避免一次性占用大量内存。

    只入库「整数答案且答案在 0-100」的题，保证默认模式的题目质量；
    返回实际写入的数量（可能少于请求值）。
    """
    if type(count) is not int or not 1 <= count <= 1000:
        raise ValueError('每次只能生成 1 到 1000 题')
    if type(batch) is not int or not 1 <= batch <= 200:
        raise ValueError('批次大小必须为 1 到 200')
    total = 0
    guard = 0
    cfg = cfg or QuestionConfig(num_range=100)
    deadline = time.monotonic() + 5
    while total < count and guard < 20 and time.monotonic() < deadline:
        guard += 1
        n = min(batch, count - total)
        qs = generate_batch(n, cfg=cfg, seed=seed, deadline=deadline)
        for expr, ans_text, ans in qs:
            if time.monotonic() >= deadline:
                break
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
    """把用户输入解析成 Fraction；支持整数/小数/分数/带分数，失败返回 None。

    先做白名单正则与长度限制，再单独限制科学计数法的指数，
    避免 ``1e999999`` 这类输入在 Fraction 里展开成天文数字。
    """
    s = str(text).strip()
    if len(s) > 128 or not re.fullmatch(r'[0-9eE+./\-\s]+', s):
        return None
    for exponent in re.findall(r'[eE]([+-]?\d+)', s):
        if len(exponent.lstrip('+-')) > 3 or abs(int(exponent)) > 100:
            return None
    if not s:
        return None
    if ' ' in s:
        # 带分数： "1 1/2" 表示 1.5
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
    """批改单题，返回 ``(是否正确, 标准答案文本, 用户答案)``。"""
    ok, std = solve(expr)
    if not ok:
        return False, None, user_answer

    std_text = format_answer(std, allow_fraction=True)
    uv = parse_user_answer(user_answer)
    if uv is None:
        return False, std_text, user_answer
    return uv == std, std_text, user_answer


def grade_batch(items):
    """批量批改；items 为 ``[(expr, user_answer), ...]``，返回逐题结果列表。"""
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
