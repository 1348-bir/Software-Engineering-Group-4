# game_24/engine.py
"""
24 点游戏引擎：
  - 给定 4 个数字，用 + - × ÷ 和括号算出 24
  - 支持求解所有解、判断用户解是否正确、随机出题
"""

import random
import re
from math_practice.engine import solve



# 复用数学练习的精确 Fraction 求值；24 点只开放四则运算。
def evaluate(expr):
    if not isinstance(expr, str) or len(expr) > 512:
        return False, None
    expr = expr.replace('*', '×').replace('/', '÷')
    if not re.fullmatch(r'[0-9\s+×÷()\-]+', expr):
        return False, None
    tokens = re.findall(r'[0-9]+|[^\s]', expr)
    expect_operand, depth = True, 0
    for token in tokens:
        if token.isdigit():
            if not expect_operand:
                return False, None
            expect_operand = False
        elif token == '(':
            if not expect_operand:
                return False, None
            depth += 1
        elif token == ')':
            if expect_operand or depth == 0:
                return False, None
            depth -= 1
        else:
            if expect_operand:
                return False, None
            expect_operand = True
    if expect_operand or depth:
        return False, None
    return solve(expr)


# ---------------- 求解所有 24 点解 ----------------

def _combine(a, b):
    """a 和 b 能通过一次运算得到的所有 (值, 表达式) 组合"""
    res = []
    res.append((a[0] + b[0], f"({a[1]} + {b[1]})"))
    res.append((a[0] - b[0], f"({a[1]} - {b[1]})"))
    res.append((b[0] - a[0], f"({b[1]} - {a[1]})"))
    res.append((a[0] * b[0], f"({a[1]} × {b[1]})"))
    if b[0] != 0:
        res.append((a[0] / b[0], f"({a[1]} ÷ {b[1]})"))
    if a[0] != 0:
        res.append((b[0] / a[0], f"({b[1]} ÷ {a[1]})"))
    return res


def solve_24(nums, target=24, eps=1e-6):
    """
    给定 4 个数字，返回所有能算出 target 的表达式（去重）。
    用递归 + 两两合并的方式枚举所有可能。
    """
    items = [(n, str(n)) for n in nums]
    results = set()

    def dfs(arr):
        if len(arr) == 1:
            val, expr = arr[0]
            if abs(val - target) < eps:
                results.add(expr)
            return
        for i in range(len(arr)):
            for j in range(len(arr)):
                if i == j:
                    continue
                rest = [arr[k] for k in range(len(arr)) if k != i and k != j]
                for val, expr in _combine(arr[i], arr[j]):
                    dfs(rest + [(val, expr)])

    dfs(items)
    return sorted(results)


def has_solution(nums):
    """判断这 4 个数字是否有解"""
    return len(solve_24(nums)) > 0


def make_puzzle(max_value=13, ensure_solvable=True, max_tries=200):
    """
    随机生成一道 24 点题目（4 个数字）。
    max_value: 数字上限，默认 13（扑克牌 A~K）
    ensure_solvable: 是否保证有解
    """
    for _ in range(max_tries):
        nums = [random.randint(1, max_value) for _ in range(4)]
        if not ensure_solvable or has_solution(nums):
            return nums
    # 兜底：返回一个一定有解的题
    return [4, 6, 2, 3]


def check_user_solution(nums, expr):
    """
    检查用户的表达式是否正确。
    返回 (是否正确, 错误原因, 标准答案列表)
    条件：
      - 表达式能算出来
      - 结果等于 24
      - 用到的数字正好是给定的 4 个（每个用一次）
    """
    ok, val = evaluate(expr)
    if not ok:
        return False, "表达式无法计算", []

    if abs(val - 24) > 1e-6:
        return False, f"结果是 {val}，不是 24", solve_24(nums)

    # 提取表达式里的数字，检查是否和题目一致
    used = []
    i = 0
    while i < len(expr):
        if expr[i].isdigit():
            num = ''
            while i < len(expr) and expr[i].isdigit():
                num += expr[i]
                i += 1
            used.append(int(num))
            continue
        i += 1

    if sorted(used) != sorted(nums):
        return False, f"数字不对，题目是 {nums}，你用了 {used}", solve_24(nums)

    return True, "", solve_24(nums)