# game_24/db.py
import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'game24.db')


class Game24DB:
    def __init__(self, path=DB_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self._init()

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
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

    def recent_attempts(self, user_id=None, limit=100):
        with self._conn() as conn:
            if user_id:
                rows = conn.execute(
                    'SELECT * FROM g24_attempt WHERE user_id=? ORDER BY id DESC LIMIT ?',
                    (user_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT * FROM g24_attempt ORDER BY id DESC LIMIT ?',
                    (limit,)
                ).fetchall()
            return [dict(r) for r in rows]

    def accuracy(self, user_id=None):
        with self._conn() as conn:
            if user_id:
                row = conn.execute(
                    'SELECT COUNT(*) AS total, SUM(is_correct) AS correct '
                    'FROM g24_attempt WHERE user_id=?',
                    (user_id,)
                ).fetchone()
            else:
                row = conn.execute(
                    'SELECT COUNT(*) AS total, SUM(is_correct) AS correct '
                    'FROM g24_attempt'
                ).fetchone()
            total = row['total'] or 0
            correct = row['correct'] or 0
            return {
                'total': total,
                'correct': correct,
                'accuracy': (correct / total) if total else 0.0,
            }