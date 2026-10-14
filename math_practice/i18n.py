# math_practice/i18n.py
TRANSLATIONS = {
    'zh': {
        'title': '数学练习系统',
        'start': '开始练习',
        'submit': '提交答案',
        'history': '历史记录',
        'accuracy': '正确率',
        'total': '总题数',
        'correct': '答对',
        'upload': '上传图片识别',
        'result': '结果',
        'standard': '标准答案',
        'your_answer': '你的答案',
        'no_record': '暂无记录',
        'switch_lang': '语言',
        'question': '第 {n} 题',
        'expr_placeholder': '请输入答案',
        'back_home': '返回个人主页',
    },
    'en': {
        'title': 'Math Practice',
        'start': 'Start',
        'submit': 'Submit',
        'history': 'History',
        'accuracy': 'Accuracy',
        'total': 'Total',
        'correct': 'Correct',
        'upload': 'Upload Image',
        'result': 'Result',
        'standard': 'Standard',
        'your_answer': 'Your Answer',
        'no_record': 'No records',
        'switch_lang': 'Language',
        'question': 'Question {n}',
        'expr_placeholder': 'Enter answer',
        'back_home': 'Back to Home',
    },
    'ja': {
        'title': '数学練習',
        'start': '開始',
        'submit': '提出',
        'history': '履歴',
        'accuracy': '正解率',
        'total': '総問題数',
        'correct': '正解',
        'upload': '画像アップロード',
        'result': '結果',
        'standard': '正解',
        'your_answer': 'あなたの答え',
        'no_record': '記録なし',
        'switch_lang': '言語',
        'question': '第 {n} 問',
        'expr_placeholder': '答えを入力',
        'back_home': 'ホームへ戻る',
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