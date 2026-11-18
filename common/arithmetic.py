"""Bounded Fraction arithmetic shared by practice, OCR and 24-point."""
import re
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


def to_rpn(tokens, allow_unary=True):
    """Validate syntax once and convert infix tokens to reverse Polish form."""
    output, stack = [], []
    expect_operand = True
    for tok in tokens:
        if _is_num(tok):
            if not expect_operand:
                raise ValueError('缺少运算符')
            output.append(tok)
            expect_operand = False
        elif tok == '(':
            if not expect_operand:
                raise ValueError('括号前缺少运算符')
            stack.append(tok)
        elif tok == ')':
            if expect_operand:
                raise ValueError('缺少操作数')
            while stack and stack[-1] != '(':
                output.append(stack.pop())
            if not stack:
                raise ValueError('括号不匹配')
            stack.pop()
        else:
            if expect_operand:
                if tok != '-' or not allow_unary:
                    raise ValueError('缺少操作数')
                tok = 'u-'
            while (stack and stack[-1] != '(' and
                   (PRECEDENCE[stack[-1]] > PRECEDENCE[tok] or
                    (PRECEDENCE[stack[-1]] == PRECEDENCE[tok] and tok not in RIGHT_ASSOC))):
                output.append(stack.pop())
            stack.append(tok)
            expect_operand = True
    if expect_operand:
        raise ValueError('缺少操作数')
    while stack:
        if stack[-1] == '(':
            raise ValueError('括号不匹配')
        output.append(stack.pop())
    return output


def apply_operation(op, a, b):
    """All consumers use the same exact, bounded binary arithmetic."""
    if op == '+': value = a + b
    elif op == '-': value = a - b
    elif op == '×': value = a * b
    elif op == '÷': value = a / b
    elif op == '^': value = bounded_power(a, b)
    else: raise ValueError('未知运算符')
    return bounded_value(value)


def eval_rpn(rpn, cfg=None):
    stack = []
    if cfg is not None and not cfg.allow_negative and 'u-' in rpn:
        raise ValueError('不允许负数')
    for tok in rpn:
        if _is_num(tok):
            value = _parse_num(tok)
            if cfg is not None and abs(value) > cfg.num_range:
                raise ValueError('运算数超出范围')
            stack.append(value)
        elif tok == 'u-':
            stack.append(-stack.pop())
        else:
            b, a = stack.pop(), stack.pop()
            if cfg is not None:
                if tok == '÷' and not cfg.allow_remainder and not cfg.allow_fraction:
                    if b == 0 or a.denominator != 1 or b.denominator != 1 or a % b:
                        raise ValueError('必须整除')
                if tok == '^' and b < 0:
                    raise ValueError('不允许负指数')
            value = apply_operation(tok, a, b)
            if cfg is not None and not cfg.allow_negative and value < 0:
                raise ValueError('不允许负数结果')
            stack.append(value)
    if len(stack) != 1:
        raise ValueError('表达式非法')
    value = stack[0]
    if cfg is not None:
        lo, hi = cfg.answer_range
        if not lo <= value <= hi:
            raise ValueError('答案超出范围')
        if not cfg.allow_fraction and not cfg.allow_remainder and value.denominator != 1:
            raise ValueError('不允许分数结果')
    return value


def solve(expr, *, allow_unary=True):
    """纯求值（Fraction），不做配置校验。返回 ``(是否合法, Fraction 值)``。"""
    try:
        rpn = to_rpn(tokenize(expr), allow_unary=allow_unary)
        val = eval_rpn(rpn)
    except Exception:
        return False, None
    return True, val


