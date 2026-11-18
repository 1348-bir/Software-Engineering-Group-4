"""Short-lived SQLite connections and queries shared by game databases."""
import os
import sqlite3
from contextlib import contextmanager


class AttemptDatabase:
    """Subclasses provide their schema and trusted table/column identifiers."""

    attempt_table = None
    success_column = 'is_correct'

    def __init__(self, path):
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

    def recent_attempts(self, user_id=None, limit=100):
        """Return newest records; an omitted user selects the admin view."""
        where = ' WHERE user_id=?' if user_id else ''
        params = (user_id, limit) if user_id else (limit,)
        with self._conn() as conn:
            rows = conn.execute(
                f'SELECT * FROM {self.attempt_table}{where} ORDER BY id DESC LIMIT ?',
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def _success_stats(self, user_id=None, count_key='correct', rate_key='accuracy'):
        where = ' WHERE user_id=?' if user_id else ''
        params = (user_id,) if user_id else ()
        with self._conn() as conn:
            row = conn.execute(
                f'SELECT COUNT(*) AS total, SUM({self.success_column}) AS successes '
                f'FROM {self.attempt_table}{where}', params,
            ).fetchone()
        total = row['total'] or 0
        successes = row['successes'] or 0
        return {
            'total': total,
            count_key: successes,
            rate_key: successes / total if total else 0.0,
        }
