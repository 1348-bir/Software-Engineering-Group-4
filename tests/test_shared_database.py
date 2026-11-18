"""Database contracts shared by the three games."""
import tempfile
import unittest
from pathlib import Path

from dice_game.db import DiceDB
from game_24.db import Game24DB
from math_practice.db import MathDB



def add_attempt(db, user, success):
    if isinstance(db, MathDB):
        db.add_attempt(user, '2+3', '5', 5, success)
    elif isinstance(db, Game24DB):
        db.add_attempt(user, [1, 2, 3, 4], '1*2*3*4', success)
    else:
        db.add_attempt(user, 3, 4, success)


def stats(db, user=None):
    return db.stats(user) if isinstance(db, DiceDB) else db.accuracy(user)


def expected(db, total, successes, rate):
    if isinstance(db, DiceDB):
        return {'total': total, 'wins': successes, 'win_rate': rate}
    return {'total': total, 'correct': successes, 'accuracy': rate}


class SharedDatabaseTests(unittest.TestCase):
    def test_empty_history_and_statistics(self):
        for cls in (MathDB, Game24DB, DiceDB):
            with self.subTest(database=cls.__name__), tempfile.TemporaryDirectory() as folder:
                database = cls(Path(folder) / "nested" / "attempts.db")
                assert database.recent_attempts() == []
                assert stats(database) == expected(database, 0, 0, 0.0)
                assert stats(database, 'unknown') == expected(database, 0, 0, 0.0)


    def test_user_isolation_admin_aggregate_and_history_limits(self):
        for cls in (MathDB, Game24DB, DiceDB):
            with self.subTest(database=cls.__name__), tempfile.TemporaryDirectory() as folder:
                database = cls(Path(folder) / "nested" / "attempts.db")
                add_attempt(database, 'alice', True)
                add_attempt(database, 'bob', False)
                add_attempt(database, 'alice', False)
                assert [r['user_id'] for r in database.recent_attempts()] == ['alice', 'bob', 'alice']
                assert [r['id'] for r in database.recent_attempts('alice', 1)] == [3]
                assert database.recent_attempts('unknown') == []
                assert stats(database, 'alice') == expected(database, 2, 1, 0.5)
                assert stats(database, 'bob') == expected(database, 1, 0, 0.0)
                assert stats(database) == expected(database, 3, 1, 1 / 3)


    def test_attempt_roundtrip_survives_reopening(self):
        for cls in (MathDB, Game24DB, DiceDB):
            with self.subTest(database=cls.__name__), tempfile.TemporaryDirectory() as folder:
                database = cls(Path(folder) / "nested" / "attempts.db")
                add_attempt(database, 'alice', True)
                reopened = type(database)(database.path)
                row = reopened.recent_attempts('alice')[0]
                assert row['user_id'] == 'alice'
                assert row['created_at']
                if isinstance(database, MathDB):
                    assert (row['expr'], row['user_answer'], row['standard'], row['is_correct'], row['source']) == ('2+3', '5', 5, 1, 'manual')
                elif isinstance(database, Game24DB):
                    assert (row['nums'], row['user_expr'], row['is_correct'], row['reason']) == ('1,2,3,4', '1*2*3*4', 1, '')
                else:
                    assert (row['d1'], row['d2'], row['total'], row['is_win']) == (3, 4, 7, 1)
