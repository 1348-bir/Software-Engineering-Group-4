# math_practice/db.py
"""数学练习的 SQLite 存取：题库（mp_question）与作答记录（mp_attempt）。

没有 ORM，直接用 sqlite3：每次操作开一个短连接，用完立刻关闭，
避免 Flask 多线程下共享连接带来的问题。数据库文件默认放在包的 data/ 目录。
"""
import os
from common.database import AttemptDatabase
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'math.db')


class MathDB(AttemptDatabase):
    """题库与作答记录的数据访问对象。"""

    attempt_table = 'mp_attempt'

    def __init__(self, path=DB_PATH):
        super().__init__(path)

    def _init(self):
        """建表：题库用 (expr, answer)，作答记录额外保存用户答案与是否答对。"""
        with self._conn() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS mp_question (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    expr TEXT UNIQUE NOT NULL,
                    answer INTEGER NOT NULL
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS mp_attempt (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    expr TEXT NOT NULL,
                    user_answer TEXT,
                    standard INTEGER,
                    is_correct INTEGER,
                    source TEXT,
                    created_at TEXT
                )
            ''')
            conn.commit()

    def add_question(self, expr, answer):
        """插入一道题；expr 有唯一约束，重复时静默忽略（INSERT OR IGNORE）。"""
        with self._conn() as conn:
            conn.execute(
                'INSERT OR IGNORE INTO mp_question (expr, answer) VALUES (?, ?)',
                (expr, answer)
            )
            conn.commit()

    def question_count(self):
        """返回题库中的题目总数。"""
        with self._conn() as conn:
            row = conn.execute('SELECT COUNT(*) AS c FROM mp_question').fetchone()
            return row['c']

    def random_questions(self, n=10):
        """随机取 n 道题，返回 ``[(expr, answer), ...]``。"""
        with self._conn() as conn:
            rows = conn.execute(
                'SELECT expr, answer FROM mp_question ORDER BY RANDOM() LIMIT ?',
                (n,)
            ).fetchall()
            return [(r['expr'], r['answer']) for r in rows]

    def add_attempt(self, user_id, expr, user_answer, standard,
                    is_correct, source='manual'):
        """写入一条作答记录；布尔值存成 0/1，时间戳用本地时间字符串。"""
        with self._conn() as conn:
            conn.execute('''
                INSERT INTO mp_attempt
                (user_id, expr, user_answer, standard, is_correct, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id, expr, str(user_answer), standard,
                1 if is_correct else 0, source,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))
            conn.commit()

    def accuracy(self, user_id=None):
        """统计作答数、正确数与正确率。"""
        return self._success_stats(user_id)
