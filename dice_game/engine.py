# dice_game/engine.py
"""
骰子游戏引擎：
  - 随机掷两个骰子（1~6）
  - 点数总和等于 7 即获胜（对应需求：A player rolls two dices,
    If the total is 7, the player wins; otherwise, loses）
"""
import random


def roll_dice():
    """掷两个骰子，返回 (d1, d2)，各为 1~6 的随机整数"""
    return random.randint(1, 6), random.randint(1, 6)


def is_win(d1, d2):
    """点数总和为 7 则获胜"""
    return d1 + d2 == 7
