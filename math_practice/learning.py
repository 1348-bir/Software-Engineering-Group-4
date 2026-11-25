"""Session-scoped learning evidence and bounded, mistake-based practice."""
import random
import re
from common.arithmetic import solve, tokenize

LIMIT = 10000


def category(expr):
    tokens = tokenize(expr)
    if any('/' in t for t in tokens):
        return '分数运算'
    if any(t == '-' and (i == 0 or tokens[i-1] in '(+-×÷^') for i, t in enumerate(tokens)):
        return '负数运算'
    if '(' in tokens:
        return '括号运算'
    if '^' in tokens:
        return '乘方运算'
    ops = set(tokens) & set('+-×÷')
    if len(ops) > 1:
        return '混合运算'
    return {'+': '加法', '-': '减法', '×': '乘法', '÷': '除法'}.get(next(iter(ops), ''), '基础数值')


def build_report(rows):
    truncated = len(rows) > LIMIT
    rows = rows[:LIMIT]  # newest first, as returned by the database
    groups, mistakes = {}, {}
    excluded = 0
    for row in rows:
        expr = row['expr']
        if not solve(expr)[0]:
            excluded += 1
            continue
        kind = category(expr)
        group = groups.setdefault(kind, dict(category=kind, total=0, wrong=0))
        group['total'] += 1
        group['wrong'] += int(not row['is_correct'])
        key = ''.join(tokenize(expr))
        item = mistakes.setdefault(key, dict(expr=expr, category=kind, attempts=0, wrong=0,
            resolved=bool(row['is_correct']), last_answer=row['user_answer'],
            standard=row['standard'], last_at=row['created_at']))
        item['attempts'] += 1
        item['wrong'] += int(not row['is_correct'])
    groups = list(groups.values())
    for g in groups:
        g['error_rate'] = g['wrong'] / g['total']
        g['sample_small'] = g['total'] < 5
    groups.sort(key=lambda g: (-g['wrong'], -g['error_rate'], g['category']))
    wrongbook = [m for m in mistakes.values() if m['wrong']]
    wrongbook.sort(key=lambda m: (m['resolved'], -m['wrong'], m['expr']))
    total = sum(g['total'] for g in groups)
    wrong = sum(g['wrong'] for g in groups)
    focus = {'加法': '基础加法及进位题', '减法': '基础减法及退位题',
             '乘法': '乘法口诀与同范围乘法题', '除法': '整除及除法检验题',
             '分数运算': '通分、约分和分数四则题', '负数运算': '符号判断与负数四则题',
             '括号运算': '先括号、后乘除、再加减的运算顺序题',
             '乘方运算': '乘方含义及与四则运算结合的题', '混合运算': '乘除优先和同级从左到右的混合题',
             '基础数值': '数值与答案格式核对'}
    advice = [dict(category=g['category'], wrong=g['wrong'], total=g['total'],
        examples=[m['expr'] for m in wrongbook if m['category'] == g['category']][:3],
        text=f"优先练习{g['category']}：已做 {g['total']} 题，答错 {g['wrong']} 次。"
             + '建议练习' + focus[g['category']] + '。'
             + ('样本少于 5 题，建议继续练习后再判断掌握情况。' if g['sample_small'] else '先重做错题，再完成同类变式。'))
        for g in groups if g['wrong']]
    return dict(total=total, correct=total-wrong, wrong=wrong,
        accuracy=(total-wrong)/total if total else 0, categories=groups, mistakes=wrongbook,
        unresolved=sum(not m['resolved'] for m in wrongbook), recommendations=advice,
        excluded=excluded, truncated=truncated,
        scope='当前浏览器会话最近 10000 条数学练习记录；题型按分数、负数、括号、乘方、混合、单一运算依次归类。优先级按答错次数、错误率排序；最近答对记为已订正，不等同于长期掌握。')


def targeted(report, count=10, kind=None):
    pool = [m for m in report['mistakes'] if (not kind or m['category'] == kind)]
    pool.sort(key=lambda m: (m['resolved'], -m['wrong']))
    if not pool:
        raise ValueError('该题型还没有错题，请先完成一次练习并提交答案。')
    questions, seen = [], set()
    # Original errors first; fill the rest with variants of the same structure.
    for m in pool[:max(1, count // 2)]:
        if m['expr'] not in seen:
            questions.append(dict(expr=m['expr'], category=m['category'], mode='错题重做'))
            seen.add(m['expr'])
    for _ in range(count * 60):
        if len(questions) >= count:
            break
        m = random.choice(pool)
        expr = re.sub(r'\d+', lambda match: str(random.randint(1, min(99, max(10, int(match.group()) * 2)))), m['expr'])
        ok, answer = solve(expr)
        if ok and expr not in seen and category(expr) == m['category']:
            # Preserve integer-only exercises, rather than introducing unexpected fractions.
            original = solve(m['expr'])[1]
            if original.denominator == 1 and answer.denominator != 1:
                continue
            seen.add(expr)
            questions.append(dict(expr=expr, category=m['category'], mode='同类变式'))
    return questions
