# game_24/engine.py
"""24 点游戏引擎。

职责：
1. 出题：随机生成 4 个 1..13 的数字，默认保证有解；
2. 求解：递归两两合并，枚举所有能算出 24 的表达式；
3. 判题：校验用户表达式——能求值、结果等于 24、且四个数字各用一次。

求值不自己实现，而是复用 ``common.arithmetic.solve``：
那里用逆波兰 + Fraction 精确计算，避免 1/3 这类中间结果出现浮点误差。
"""

import random
import re

from fractions import Fraction
from common.arithmetic import solve, apply_operation, MAX_NUMBER_DIGITS


def valid_numbers(nums, minimum=1, maximum=13):
    """Validate before Fraction conversion; booleans and numeric strings are invalid."""
    return (isinstance(nums, (list, tuple)) and len(nums) == 4
            and all(type(n) is int and minimum <= n <= maximum for n in nums))


# 复用数学练习的精确 Fraction 求值；24 点只开放四则运算。
def evaluate(expr):
    """校验并计算用户表达式，返回 ``(是否合法, Fraction 值)``。

    先用正则做字符白名单（只允许数字、空格、加减乘除与括号），
    语法校验与精确计算统一由共享解析器负责；游戏禁用一元负号。
    """
    if not isinstance(expr, str) or len(expr) > 512:
        return False, None
    # 允许用户输入 * 和 /，统一换成显示用的 × 和 ÷。
    expr = expr.replace('*', '×').replace('/', '÷')
    if not re.fullmatch(r'[0-9\s+×÷()\-]+', expr):
        return False, None
    return solve(expr, allow_unary=False)


# ---------------- 求解所有 24 点解 ----------------

def _combine(a, b):
    """a 和 b 能通过一次运算得到的所有 (值, 表达式) 组合。

    a、b 都是 ``(值, 表达式文本)`` 二元组；减法与除法都给出两个方向，
    保证 3-4 和 4-3 都能被枚举到。
    """
    res = []
    for left, right, op in ((a, b, '+'), (a, b, '-'), (b, a, '-'),
                            (a, b, '×'), (a, b, '÷'), (b, a, '÷')):
        try:
            value = apply_operation(op, left[0], right[0])
        except (ZeroDivisionError, ValueError):
            continue
        res.append((value, f'({left[1]} {op} {right[1]})'))
    return res


def solve_24(nums, target=24, eps=1e-6):
    """
    给定 4 个数字，返回所有能算出 target 的表达式（已去重、已排序）。
    用递归 + 两两合并的方式枚举所有可能。
    """
    bound = 10 ** MAX_NUMBER_DIGITS - 1
    if not valid_numbers(nums, -bound, bound):
        return []
    items = [(Fraction(n), str(n)) for n in nums]
    results = set()

    def dfs(arr):
        """把当前这组数两两合并，直到只剩一个数；等于目标就收集表达式。"""
        if len(arr) == 1:
            val, expr = arr[0]
            if val == target:
                results.add(expr)
            return
        for i in range(len(arr)):
            for j in range(len(arr)):
                if i == j:
                    continue
                # 取出剩下的数，把「合并后的值」加回去继续递归。
                rest = [arr[k] for k in range(len(arr)) if k != i and k != j]
                for val, expr in _combine(arr[i], arr[j]):
                    dfs(rest + [(val, expr)])

    dfs(items)
    return sorted(results)


def has_solution(nums):
    """判断这 4 个数字是否有解（用于出题时过滤无解题）。"""
    return len(solve_24(nums)) > 0


def make_puzzle(max_value=13, ensure_solvable=True, max_tries=200):
    """
    随机生成一道 24 点题目（4 个数字）。

    max_value：数字上限，默认 13（扑克牌 A~K）
    ensure_solvable：是否保证有解
    max_tries：最多重试次数，用尽后回退到一道固定的有解题
    """
    for _ in range(max_tries):
        nums = [random.randint(1, max_value) for _ in range(4)]
        if not ensure_solvable or has_solution(nums):
            return nums
    # 兜底：返回一个一定有解的题（4×6=24，2 和 3 可组合成 1 或消耗掉）。
    return [4, 6, 2, 3]


def check_user_solution(nums, expr):
    """
    检查用户的表达式是否正确。

    返回 ``(是否正确, 错误原因, 标准答案列表)``，判定条件依次是：
      1. 表达式能算出来；
      2. 结果等于 24；
      3. 用到的数字正好是给定的 4 个（每个用一次）。
    """
    ok, val = evaluate(expr)
    if not ok:
        return False, "表达式无法计算", []

    if val != 24:
        return False, f"结果是 {val}，不是 24", solve_24(nums)

    # 从表达式里提取所有整数，检查是否和题目给的数字一致。
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
