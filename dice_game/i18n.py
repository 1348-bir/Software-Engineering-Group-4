# dice_game/i18n.py
TRANSLATIONS = {
    'zh': {
        'title': '骰子游戏',
        'roll': '掷骰子',
        'history': '历史记录',
        'back_home': '返回个人主页',
        'hint': '掷两个骰子，点数总和为 7 即获胜',
        'win_msg': '恭喜！你赢了！',
        'lose_msg': '再试一次…',
        'total': '总次数',
        'wins': '获胜',
        'win_rate': '胜率',
        'no_record': '暂无记录',
        'result': '结果',
        'time': '时间',
        'howto_title': '如何使用',
        'howto_s1_title': '掷出两个骰子',
        'howto_s1_desc': '点击「掷骰子」，两个骰子随机生成 1-6 的点数。',
        'howto_s2_title': '计算总和',
        'howto_s2_desc': '系统自动计算两个骰子的点数之和。',
        'howto_s3_title': '7 即获胜',
        'howto_s3_desc': '总数为 7 判定获胜，其余点数视为失败。',
        'howto_tip': '提示：两个骰子和为 7 的概率是 5/36（约 13.9%）。',
        'howto_history_note': '这里记录了每次掷骰的结果与胜率统计。',
    },
    'en': {
        'title': 'Dice Game',
        'roll': 'Roll',
        'history': 'History',
        'back_home': 'Back to Home',
        'hint': 'Roll two dice. If the total is 7, you win!',
        'win_msg': 'Congratulations! You won the game!',
        'lose_msg': 'Try again ...',
        'total': 'Total',
        'wins': 'Wins',
        'win_rate': 'Win Rate',
        'no_record': 'No records',
        'result': 'Result',
        'time': 'Time',
        'howto_title': 'How to use',
        'howto_s1_title': 'Roll two dice',
        'howto_s1_desc': 'Click Roll; each die shows a random value from 1 to 6.',
        'howto_s2_title': 'Add them up',
        'howto_s2_desc': 'The system sums the two dice automatically.',
        'howto_s3_title': '7 wins',
        'howto_s3_desc': 'A total of 7 is a win; any other total is a loss.',
        'howto_tip': 'Tip: the probability of rolling a total of 7 is 5/36 (about 13.9%).',
        'howto_history_note': 'Every roll and your win-rate stats are listed here.',
    },
    'ja': {
        'title': 'ダイスゲーム',
        'roll': 'サイコロを振る',
        'history': '履歴',
        'back_home': 'ホームへ戻る',
        'hint': 'サイコロを 2 つ振り、合計が 7 なら勝ち',
        'win_msg': 'おめでとう！勝ちました！',
        'lose_msg': 'もう一度挑戦...',
        'total': '総回数',
        'wins': '勝利',
        'win_rate': '勝率',
        'no_record': '記録なし',
        'result': '結果',
        'time': '時間',
        'howto_title': '使い方',
        'howto_s1_title': 'サイコロを 2 つ振る',
        'howto_s1_desc': '「サイコロを振る」で 1-6 の目がランダムに出ます。',
        'howto_s2_title': '合計を計算',
        'howto_s2_desc': '2 つのサイコロの合計を自動で計算します。',
        'howto_s3_title': '合計 7 で勝ち',
        'howto_s3_desc': '合計が 7 なら勝ち、それ以外は負けです。',
        'howto_tip': 'ヒント：合計が 7 になる確率は 5/36（約 13.9%）です。',
        'howto_history_note': '毎回の結果と勝率の統計が表示されます。',
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
