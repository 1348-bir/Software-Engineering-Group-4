"""Explainable per-category difficulty decisions and bounded question generation."""
import random
import re
import time
from common.arithmetic import solve
from .learning import category

CATEGORIES = ('加法', '减法', '乘法', '除法', '混合运算', '括号运算', '负数运算', '分数运算', '乘方运算')
RANGES = (10, 20, 50, 100)


def choose_level(rows, kind='auto'):
    valid = [r for r in rows if solve(r['expr'])[0]]
    if kind == 'auto':
        groups = {}
        for row in valid[:100]:
            k = category(row['expr'])
            if k in CATEGORIES:
                g = groups.setdefault(k, [0, 0])
                g[0] += 1
                g[1] += int(not row['is_correct'])
        weak = [k for k in groups if groups[k][1]]
        kind = (max(weak, key=lambda k: (groups[k][1], groups[k][1]/groups[k][0])) if weak
                else next((category(r['expr']) for r in valid if category(r['expr']) in CATEGORIES), '加法'))
    if kind not in CATEGORIES:
        raise ValueError('请选择支持的题型')
    recent = [r for r in valid if category(r['expr']) == kind][:20]
    tagged = [r for r in recent if re.fullmatch(r'adaptive:' + re.escape(kind) + r':[1-4]', r.get('source') or '')]
    old = int(tagged[0]['source'].rsplit(':', 1)[1]) if tagged else 1
    samples = [r for r in recent if r.get('source') == f'adaptive:{kind}:{old}'] if tagged else recent
    correct = sum(bool(r['is_correct']) for r in samples)
    rate = correct/len(samples) if samples else None
    level = old
    if len(samples) < 5:
        reason = '同类同难度有效记录少于 5 题，保持当前难度，先积累练习样本。'
    elif rate >= .85:
        level = min(4, old + 1)
        reason = '正确率达到 85%，提升一级。' if level > old else '已达到最高难度，继续巩固。'
    elif rate < .60:
        level = max(1, old - 1)
        reason = '正确率低于 60%，降低一级巩固基础。' if level < old else '从基础难度巩固，优先提高正确率。'
    else:
        reason = '正确率处于 60% 至 85% 区间，保持当前难度。'
    return dict(category=kind, level=level, previous_level=old, samples=len(samples), accuracy=rate,
                num_range=RANGES[level-1], reason=reason,
                basis='在最近 1000 条记录中，参考最近 20 次同类有效作答；已有自适应记录时只使用当前难度记录，否则使用同类记录。至少 5 题后调整；综合推荐参考最近 100 次有效作答。')


def generate_adaptive(rows, count, kind='auto'):
    decision = choose_level(rows, kind)
    level, size, kind = decision['level'], decision['num_range'], decision['category']
    result, seen = [], set()
    deadline = time.monotonic() + 1.5
    for _ in range(count * 300):
        if len(result) >= count or time.monotonic() > deadline:
            break
        a, b, c = (random.randint(1, size) for _ in range(3))
        terms = 2 if level <= 2 else 3 if level == 3 else 4
        if kind in ('加法', '减法', '乘法'):
            op = {'加法': '+', '减法': '-', '乘法': '×'}[kind]
            nums = [random.randint(1, size) for _ in range(terms)]
            if kind == '减法':
                nums[0] += sum(nums[1:])
            expr = op.join(map(str, nums))
        elif kind == '除法':
            expr = f'{a*b}÷{b}' if level <= 2 else f'{a*b*c}÷{b}÷{c}'
        elif kind == '混合运算':
            expr = f'{a}+{b}×{c}' if level <= 2 else f'{a}×{b}+{c}÷{random.randint(1, size)}'
        elif kind == '括号运算':
            expr = f'({a}+{b})×{c}' if level <= 2 else f'({a}+{b})×({c}+{random.randint(1,size)})'
        elif kind == '负数运算':
            expr = f'-{a}+{b}' if level <= 2 else f'(-{a}+{b})×{c}'
        elif kind == '分数运算':
            d = random.randint(2, min(12, size))
            expr = f'{a}/{d}+{b}/{d}' if level == 1 else f'{a}/{d}{random.choice(["+","-","×"])}{b}/{random.randint(2,min(20,size))}'
        else:
            expr = f'{random.randint(2,min(10,size))}^{random.randint(2,min(5,level+2))}'
            if level >= 3:
                expr += f'+{a}'
        ok, value = solve(expr)
        if ok and abs(value) <= 1000000 and expr not in seen and category(expr) == kind:
            seen.add(expr)
            result.append(dict(expr=expr, category=kind, level=level))
    return dict(questions=result, count=len(result), decision=decision,
                source=f'adaptive:{kind}:{level}')
