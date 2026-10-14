# math_practice/db.py
import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'math.db')


class MathDB:
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
        with self._conn() as conn:
            conn.execute(
                'INSERT OR IGNORE INTO mp_question (expr, answer) VALUES (?, ?)',
                (expr, answer)
            )
            conn.commit()

    def question_count(self):
        with self._conn() as conn:
            row = conn.execute('SELECT COUNT(*) AS c FROM mp_question').fetchone()
            return row['c']

    def random_questions(self, n=10):
        with self._conn() as conn:
            rows = conn.execute(
                'SELECT expr, answer FROM mp_question ORDER BY RANDOM() LIMIT ?',
                (n,)
            ).fetchall()
            return [(r['expr'], r['answer']) for r in rows]

    def add_attempt(self, user_id, expr, user_answer, standard,
                    is_correct, source='manual'):
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

    def recent_attempts(self, user_id=None, limit=100):
        with self._conn() as conn:
            if user_id:
                rows = conn.execute(
                    'SELECT * FROM mp_attempt WHERE user_id=? ORDER BY id DESC LIMIT ?',
                    (user_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT * FROM mp_attempt ORDER BY id DESC LIMIT ?',
                    (limit,)
                ).fetchall()
            return [dict(r) for r in rows]

    def accuracy(self, user_id=None):
        with self._conn() as conn:
            if user_id:
                row = conn.execute(
                    'SELECT COUNT(*) AS total, SUM(is_correct) AS correct '
                    'FROM mp_attempt WHERE user_id=?',
                    (user_id,)
                ).fetchone()
            else:
                row = conn.execute(
                    'SELECT COUNT(*) AS total, SUM(is_correct) AS correct '
                    'FROM mp_attempt'
                ).fetchone()
            total = row['total'] or 0
            correct = row['correct'] or 0
            return {
                'total': total,
                'correct': correct,
                'accuracy': (correct / total) if total else 0.0,
            }