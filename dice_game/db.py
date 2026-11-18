# dice_game/db.py
"""双骰游戏的 SQLite 存取：每次投掷的两个点数、总和与胜负。

与另外两个功能各自独立建库，记录按 user_id（浏览器会话）隔离。
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'dice.db')


class DiceDB:
    """投掷记录的数据访问对象。"""

    def __init__(self, path=DB_PATH):
        """确保目录存在并建表；path 可传自定义路径（测试用临时库）。"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self._init()

    @contextmanager
    def _conn(self):
        """借出一个连接并在结束时关闭。"""
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

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

    def recent_attempts(self, user_id=None, limit=100):
        """按时间倒序取记录；传 user_id 时只取该会话的记录。"""
        with self._conn() as conn:
            if user_id:
                rows = conn.execute(
                    'SELECT * FROM dg_attempt WHERE user_id=? ORDER BY id DESC LIMIT ?',
                    (user_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT * FROM dg_attempt ORDER BY id DESC LIMIT ?',
                    (limit,)
                ).fetchall()
            return [dict(r) for r in rows]

    def stats(self, user_id=None):
        """统计投掷次数、获胜次数与胜率。"""
        with self._conn() as conn:
            if user_id:
                row = conn.execute(
                    'SELECT COUNT(*) AS total, SUM(is_win) AS wins '
                    'FROM dg_attempt WHERE user_id=?',
                    (user_id,)
                ).fetchone()
            else:
                row = conn.execute(
                    'SELECT COUNT(*) AS total, SUM(is_win) AS wins '
                    'FROM dg_attempt'
                ).fetchone()
            total = row['total'] or 0
            wins = row['wins'] or 0
            return {
                'total': total,
                'wins': wins,
                'win_rate': (wins / total) if total else 0.0,
            }
