# dice_game/db.py
"""双骰游戏的 SQLite 存取：每次投掷的两个点数、总和与胜负。

与另外两个功能各自独立建库，记录按 user_id（浏览器会话）隔离。
"""
import os
from common.database import AttemptDatabase
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'dice.db')


class DiceDB(AttemptDatabase):
    """投掷记录的数据访问对象。"""

    attempt_table = 'dg_attempt'
    success_column = 'is_win'

    def __init__(self, path=DB_PATH):
        super().__init__(path)

    def _init(self):
        """建表：同时存两个骰子与总和，便于直接查历史与统计。"""
        with self._conn() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS dg_attempt (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    d1 INTEGER NOT NULL,
                    d2 INTEGER NOT NULL,
                    total INTEGER NOT NULL,
                    is_win INTEGER,
                    created_at TEXT
                )
            ''')
            conn.commit()

    def add_attempt(self, user_id, d1, d2, is_win):
        """写入一次投掷；总和在这里直接算好，省得查询时再相加。"""
        with self._conn() as conn:
            conn.execute('''
                INSERT INTO dg_attempt
                (user_id, d1, d2, total, is_win, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                d1,
                d2,
                d1 + d2,
                1 if is_win else 0,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))
            conn.commit()

    def stats(self, user_id=None):
        """统计投掷次数、获胜次数与胜率。"""
        return self._success_stats(user_id, count_key='wins', rate_key='win_rate')
