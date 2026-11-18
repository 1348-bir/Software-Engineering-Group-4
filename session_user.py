"""练习与游戏共用的匿名浏览器身份。

没有账号体系：第一次访问时生成 16 位随机串写进 Flask 会话，
之后的练习记录、24 点作答、骰子投掷都按这个标识隔离。
"""
from uuid import uuid4

from flask import session


def current_user():
    """返回当前浏览器的匿名标识；会话里没有时生成并写入。"""
    if 'uid' not in session:
        session['uid'] = uuid4().hex[:16]
    return session['uid']
