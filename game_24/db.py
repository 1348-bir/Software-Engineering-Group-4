# game_24/db.py
"""24 点游戏的 SQLite 存取：每次作答的数字组、表达式、对错与原因。

与数学练习的表结构分开，避免两个功能的记录混在一起；
查询始终按 user_id 过滤，保证不同浏览器会话互不可见。
"""
import os
from common.database import AttemptDatabase
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'game24.db')


class Game24DB(AttemptDatabase):
    """24 点作答记录的数据访问对象。"""

    attempt_table = 'g24_attempt'

    def __init__(self, path=DB_PATH):
        super().__init__(path)

    def _init(self):
        """建表：nums 存成逗号分隔的字符串，reason 保存判错原因。"""
        with self._conn() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS g24_attempt (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    nums TEXT NOT NULL,
                    user_expr TEXT,
                    is_correct INTEGER,
                    reason TEXT,
                    created_at TEXT
                )
            ''')
            conn.commit()

    def add_attempt(self, user_id, nums, user_expr, is_correct, reason=''):
        """写入一次作答；nums 列表拼接成 "3,4,5,6" 这样的字符串。"""
        with self._conn() as conn:
            conn.execute('''
                INSERT INTO g24_attempt
                (user_id, nums, user_expr, is_correct, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                ','.join(str(n) for n in nums),
                user_expr,
                1 if is_correct else 0,
                reason,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))
            conn.commit()

    def accuracy(self, user_id=None):
        """统计作答数、正确数与正确率。"""
        return self._success_stats(user_id)
