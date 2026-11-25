import unittest
from unittest.mock import patch
from fractions import Fraction
from math_practice.engine import solve, evaluate, QuestionConfig
from game_24.engine import solve_24, check_user_solution


class SharedArithmetic(unittest.TestCase):
    def test_solver_rejects_untrusted_numbers_before_fraction_parsing(self):
        with patch('game_24.engine.Fraction', side_effect=AssertionError('must not parse')):
            self.assertEqual(solve_24(['1e1000000000', 1, 2, 3]), [])
            self.assertEqual(solve_24([10**1000, 1, 2, 3]), [])

    def test_game_api_rejects_invalid_number_types_and_ranges(self):
        from app import app
        with patch('game_24.routes.check_user_solution', return_value=(False, '', [])), patch('game_24.routes.db.add_attempt'):
            for nums in (['1e1000000000', 1, 2, 3], [True, 1, 2, 3], [14, 1, 2, 3], [0, 1, 2, 3]):
                response = app.test_client().post('/game24/api/submit', json={'nums': nums, 'expr': '1+1'})
                self.assertEqual(response.status_code, 400)

    def test_shared_parser_rejects_missing_operators(self):
        for expr in ('1 2+', '2(3)', '(2)3', '()', '3+', '(3+4'):
            with self.subTest(expr=expr):
                self.assertEqual(solve(expr), (False, None))
        self.assertEqual(solve('-2 + 3'), (True, Fraction(1)))

    def test_policy_keeps_practice_constraints(self):
        self.assertEqual(solve('3 ÷ 2'), (True, Fraction(3, 2)))
        self.assertEqual(evaluate('3 ÷ 2'), (False, None))
        self.assertEqual(evaluate('3 ÷ 2', QuestionConfig(allow_fraction=True)),
                         (True, Fraction(3, 2)))
        self.assertEqual(evaluate('1 - 2'), (False, None))
        self.assertEqual(solve('1 - 2'), (True, Fraction(-1)))

    def test_game_rejects_near_miss_exactly(self):
        # Exact result 24 + 1/10^7 used to pass the floating-point tolerance.
        self.assertFalse(check_user_solution([24, 1, 10000000, 1],
            '24+1÷10000000×1')[0])

    def test_every_solver_answer_is_exact(self):
        answers = solve_24([3, 3, 8, 8])
        self.assertTrue(answers)
        for answer in answers:
            self.assertEqual(solve(answer), (True, Fraction(24)))
