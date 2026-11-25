"""Calendar-based learning trends; empty days have no accuracy value."""
from datetime import datetime, timedelta
from common.arithmetic import solve, tokenize


def build_trends(rows, today=None):
    today = today or datetime.now().date()
    start = today - timedelta(days=13)
    days = {str(start+timedelta(days=i)): dict(date=str(start+timedelta(days=i)), total=0, correct=0, wrong=0, accuracy=None) for i in range(14)}
    dated, excluded = [], 0
    for row in rows:
        if not solve(row['expr'])[0]:
            continue
        try:
            day = datetime.fromisoformat(row['created_at']).date()
        except (ValueError, TypeError):
            excluded += 1
            continue
        if day > today:
            excluded += 1
            continue
        dated.append((day, row))
        if str(day) in days:
            d = days[str(day)]
            d['total'] += 1
            d['correct'] += int(bool(row['is_correct']))
            d['wrong'] += int(not row['is_correct'])
    for d in days.values():
        if d['total']:
            d['accuracy'] = d['correct']/d['total']

    def period(first, last):
        selected = [(day, r) for day, r in dated if first <= day <= last]
        total = len(selected)
        correct = sum(bool(r['is_correct']) for _, r in selected)
        mistakes = {}
        # Input is newest first: the first state is the latest within this period.
        for _, r in selected:
            key = ''.join(tokenize(r['expr']))
            m = mistakes.setdefault(key, dict(latest=bool(r['is_correct']), wrong=False))
            m['wrong'] |= not r['is_correct']
        wrong_items = [m for m in mistakes.values() if m['wrong']]
        corrected = sum(m['latest'] for m in wrong_items)
        return dict(start=str(first), end=str(last), total=total, correct=correct,
            accuracy=correct/total if total else None, active_days=len({day for day, _ in selected}),
            wrong_questions=len(wrong_items), corrected=corrected,
            correction_rate=corrected/len(wrong_items) if wrong_items else None)

    current = period(today-timedelta(days=6), today)
    previous = period(today-timedelta(days=13), today-timedelta(days=7))
    delta = ((current['accuracy']-previous['accuracy'])*100
             if current['accuracy'] is not None and previous['accuracy'] is not None else None)
    return dict(days=list(days.values()), current=current, previous=previous,
        accuracy_change_pp=round(delta, 2) if delta is not None else None,
        volume_change=current['total']-previous['total'], excluded_dates=excluded,
        sample_small=current['total'] < 5 or previous['total'] < 5,
        note='近 7 天包含今天，与之前 7 天比较。没有作答的日期不计算正确率。期内错题订正率按本期曾答错、且本期最近一次已答对的不同算式计算；同一题重复作答计入练习量。正确率变化也受题型与难度变化影响。')
