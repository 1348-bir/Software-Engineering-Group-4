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

# 运算符优先级：数字越大越先算；u- 表示一元负号，优先级最高。
PRECEDENCE = {
    '+': 1, '-': 1,
    '×': 2, '÷': 2,
    '^': 3,
    'u-': 4,
}

# 右结合运算符：连续出现时从右往左算（2^3^2 = 2^(3^2)）。
RIGHT_ASSOC = {'^', 'u-'}

OPS = ['+', '-', '×', '÷']

# 数字 token 的合法形态：整数，或「整数/整数」形式的分数。
_TOKEN_NUM = re.compile(r'^\d+(/\d+)?$')
MAX_EXPRESSION = 512       # 算式最大字符数
MAX_NUMBER_DIGITS = 16     # 单个运算数最大位数
MAX_VALUE_BITS = 256       # 中间结果分子/分母的位长上限
MAX_EXPONENT = 12          # 指数绝对值上限


def bounded_value(value):
    """限制 Fraction 的分子/分母位长，防止 2^2^2^2 这类算式把内存吃满。"""
    if (value.numerator.bit_length() > MAX_VALUE_BITS or
            value.denominator.bit_length() > MAX_VALUE_BITS):
        raise ValueError('计算结果过大')
    return value


def bounded_power(base, exponent):
    """幂运算：指数必须是 -12..12 的整数，结果同样受位长限制。"""
    if exponent.denominator != 1 or abs(exponent) > MAX_EXPONENT:
        raise ValueError('指数必须为 -12 到 12 的整数')
    return bounded_value(base ** int(exponent))


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

def tokenize(expr):
    """把算式切成 token：数字（可含分数）、运算符与括号。

    空格被跳过；出现其他字符直接抛错，这一层就挡住注入式输入。
    """
    if not isinstance(expr, str) or len(expr) > MAX_EXPRESSION:
        raise ValueError('算式过长或格式错误')
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
            # 分数：数字紧跟 '/数字'，例如 3/4。
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
    """判断 token 是不是数字/分数。"""
    return bool(_TOKEN_NUM.match(tok))


def _parse_num(tok):
    """把 token 解析成 Fraction；任一部分位数超限时抛错。"""
    if any(len(part) > MAX_NUMBER_DIGITS for part in tok.split('/')):
        raise ValueError('运算数过长')
    if '/' in tok:
        n, d = tok.split('/', 1)
        return Fraction(int(n), int(d))
    return Fraction(int(tok))


def to_rpn(tokens):
    """调度场算法：中缀 token -> 逆波兰 token。

    规则：数字直接输出；左括号入栈；右括号弹到左括号为止；
    运算符按优先级弹出栈顶，右结合运算符（^、u-）遇到同级时不弹。
    另外把「出现在开头或运算符后的减号」改写成一元负号 u-。
    """
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
            # 一元负号判定：前面没有操作数（开头或紧跟运算符/左括号）。
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
    """求逆波兰表达式的值（Fraction 精确运算）；除零或结果过大时抛错。"""
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
                stack.append(bounded_power(a, b))
            bounded_value(stack[-1])   # 每步都检查是否过大
    if len(stack) != 1:
        raise ValueError("表达式非法")
    return stack[0]


def solve(expr):
    """纯求值（Fraction），不做配置校验。返回 ``(是否合法, Fraction 值)``。"""
    try:
        rpn = to_rpn(tokenize(expr))
        val = eval_rpn(rpn)
    except Exception:
        return False, None
    return True, val


def evaluate(expr, cfg=None):
    """按配置校验表达式，返回 ``(是否合法, Fraction 答案)``。

    与 solve 的区别：这里除了算得出来，还要满足配置——
    运算数范围、是否允许负数、除法是否必须整除、结果是否在允许区间。
    """
    cfg = cfg or QuestionConfig()
    lo, hi = cfg.answer_range
    try:
        rpn = to_rpn(tokenize(expr))
    except Exception:
        return False, None

    # 题面负数：u- 出现在 rpn 中即代表表达式含负号。
    if not cfg.allow_negative and 'u-' in rpn:
        return False, None

    stack = []
    for tok in rpn:
        if _is_num(tok):
            try:
                v = _parse_num(tok)
            except (ValueError, ZeroDivisionError):
                return False, None
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
                # 没开余数、也没开分数时，除法必须整除。
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
                # 出题场景只允许非负整数指数。
                if b.denominator != 1 or b < 0:
                    return False, None
                try:
                    v = bounded_power(a, b)
                except (ValueError, ZeroDivisionError):
                    return False, None
            else:
                return False, None
            if not cfg.allow_negative and v < 0:
                return False, None
            try:
                stack.append(bounded_value(v))
            except ValueError:
                return False, None

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
