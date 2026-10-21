# dice_game/db.py
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'dice.db')


class DiceDB:
    def __init__(self, path=DB_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self._init()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init(self):
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
