# game_24/i18n.py
"""24 点页面的多语言文案表（中文 / English / 日本語）。

模板通过 ``t('key')`` 取词，语言由 ``get_lang()`` 决定：
优先 ``?lang=`` 查询参数，其次浏览器 Accept-Language，最后回退英文。
"""
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
        'howto_title': '如何使用',
        'howto_s1_title': '随机取牌',
        'howto_s1_desc': '点击「开始新题」，自动抽出 4 张数字牌。',
        'howto_s2_title': '凑成 24',
        'howto_s2_desc': '用 + - × ÷ 和括号，4 个数字各用一次。',
        'howto_s3_title': '提交验证',
        'howto_s3_desc': '提交表达式，系统自动判定并给出参考答案。',
        'howto_tip': '提示：大部分牌组都有多种解法，参考解答会列出所有结果。',
        'howto_history_note': '这里记录了你的 24 点答题记录与正确率变化。',
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
        'howto_title': 'How to use',
        'howto_s1_title': 'Draw cards',
        'howto_s1_desc': 'Click New Puzzle to draw 4 number cards.',
        'howto_s2_title': 'Make 24',
        'howto_s2_desc': 'Use + - × ÷ and parentheses, each number once.',
        'howto_s3_title': 'Submit to check',
        'howto_s3_desc': 'Submit your expression; the system checks it and shows answers.',
        'howto_tip': 'Tip: most puzzles have multiple solutions; the reference lists them all.',
        'howto_history_note': 'Your 24 Game attempts and accuracy trend are listed here.',
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
        'howto_title': '使い方',
        'howto_s1_title': 'カードを引く',
        'howto_s1_desc': '「新しい問題」で数字カードを 4 枚引きます。',
        'howto_s2_title': '24 を作る',
        'howto_s2_desc': '+ - × ÷ と括弧を使い、4 つの数字を 1 回ずつ。',
        'howto_s3_title': '提出して判定',
        'howto_s3_desc': '式を提出すると自動判定され、参考解答が表示されます。',
        'howto_tip': 'ヒント：多くの牌組には複数の解があります。参考解答にすべて表示されます。',
        'howto_history_note': '24ゲームの回答履歴と正解率の推移が表示されます。',
    },
}


def get_lang(request):
    """决定本次请求使用哪种语言：?lang= 优先，其次浏览器偏好，默认英文。"""
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
    """取一条文案并填充占位符；语言或键不存在时回退到中文、再回退到键名。"""
    text = TRANSLATIONS.get(lang, TRANSLATIONS['zh']).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def translator(lang):
    """返回绑定好语言的取词函数，模板里只写 ``t('key')`` 即可。"""
    return lambda key, **kw: t(key, lang, **kw)