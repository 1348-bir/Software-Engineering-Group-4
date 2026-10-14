# game_24/i18n.py
TRANSLATIONS = {
    'zh': {
        'title': '24 点游戏',
        'start': '开始新题',
        'submit': '提交答案',
        'history': '历史记录',
        'accuracy': '正确率',
        'total': '总题数',
        'correct': '答对',
        'no_record': '暂无记录',
        'back_home': '返回个人主页',
        'nums': '题目数字',
        'your_expr': '你的表达式',
        'result': '结果',
        'reason': '提示',
        'std_answers': '参考答案',
        'placeholder': '如 (3 + 4) × (6 - 2)',
        'hint_use': '用 + - × ÷ 和括号，把 4 个数字各用一次，算出 24',
        'invalid': '表达式无效',
        'answer_correct': '✓ 正确',
        'answer_wrong': '✗ 错误',
    },
    'en': {
        'title': '24 Game',
        'start': 'New Puzzle',
        'submit': 'Submit',
        'history': 'History',
        'accuracy': 'Accuracy',
        'total': 'Total',
        'correct': 'Correct',
        'no_record': 'No records',
        'back_home': 'Back to Home',
        'nums': 'Numbers',
        'your_expr': 'Your Expression',
        'result': 'Result',
        'reason': 'Hint',
        'std_answers': 'Reference Answers',
        'placeholder': 'e.g. (3 + 4) × (6 - 2)',
        'hint_use': 'Use + - × ÷ and parentheses, each number once, make 24',
        'invalid': 'Invalid expression',
        'answer_correct': '✓ Correct',
        'answer_wrong': '✗ Wrong',
    },
    'ja': {
        'title': '24ゲーム',
        'start': '新しい問題',
        'submit': '提出',
        'history': '履歴',
        'accuracy': '正解率',
        'total': '総問題数',
        'correct': '正解',
        'no_record': '記録なし',
        'back_home': 'ホームへ戻る',
        'nums': '数字',
        'your_expr': 'あなたの式',
        'result': '結果',
        'reason': 'ヒント',
        'std_answers': '参考解答',
        'placeholder': '例：(3 + 4) × (6 - 2)',
        'hint_use': '+ - × ÷ と括弧で、4 つの数字を 1 回ずつ使って 24 にする',
        'invalid': '無効な式',
        'answer_correct': '✓ 正解',
        'answer_wrong': '✗ 不正解',
    },
}


def get_lang(request):
    lang = request.args.get('lang')
    if lang in TRANSLATIONS:
        return lang
    al = request.headers.get('Accept-Language', '')
    if 'zh' in al:
        return 'zh'
    if 'ja' in al:
        return 'ja'
    return 'en'


def t(key, lang='zh', **kwargs):
    text = TRANSLATIONS.get(lang, TRANSLATIONS['zh']).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def translator(lang):
    return lambda key, **kw: t(key, lang, **kw)