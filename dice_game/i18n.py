# dice_game/i18n.py
TRANSLATIONS = {
    'zh': {
        'title': '骰子游戏',
        'roll': '掷骰子',
        'history': '历史记录',
        'back_home': '返回个人主页',
        'hint': '掷两个骰子，点数总和为 7 即获胜',
        'win_msg': '恭喜！你赢了！🎉',
        'lose_msg': '再试一次…',
        'total': '总次数',
        'wins': '获胜',
        'win_rate': '胜率',
        'no_record': '暂无记录',
        'result': '结果',
        'time': '时间',
    },
    'en': {
        'title': 'Dice Game',
        'roll': 'Roll',
        'history': 'History',
        'back_home': 'Back to Home',
        'hint': 'Roll two dice. If the total is 7, you win!',
        'win_msg': 'Congratulations! You won the game! 🎉',
        'lose_msg': 'Try again ...',
        'total': 'Total',
        'wins': 'Wins',
        'win_rate': 'Win Rate',
        'no_record': 'No records',
        'result': 'Result',
        'time': 'Time',
    },
    'ja': {
        'title': 'ダイスゲーム',
        'roll': 'サイコロを振る',
        'history': '履歴',
        'back_home': 'ホームへ戻る',
        'hint': 'サイコロを 2 つ振り、合計が 7 なら勝ち',
        'win_msg': 'おめでとう！勝ちました！🎉',
        'lose_msg': 'もう一度挑戦...',
        'total': '総回数',
        'wins': '勝利',
        'win_rate': '勝率',
        'no_record': '記録なし',
        'result': '結果',
        'time': '時間',
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
