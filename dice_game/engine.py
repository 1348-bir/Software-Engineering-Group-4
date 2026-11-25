# dice_game/engine.py
"""骰子游戏引擎：掷两个骰子（1~6），点数和为 7 即获胜。

规则对应课程需求：A player rolls two dices; if the total is 7,
the player wins; otherwise, loses.
这里只放纯规则，不涉及数据库与请求，方便单测。
"""
import random


def roll_dice():
    """掷两个骰子，返回 ``(d1, d2)``，各为 1~6 的随机整数。"""
    return random.randint(1, 6), random.randint(1, 6)


def is_win(d1, d2):
    """点数总和为 7 则获胜（共 6/36 = 1/6 的组合）。"""
    return d1 + d2 == 7
