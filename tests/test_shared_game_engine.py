import unittest
from fractions import Fraction
from game_24.engine import evaluate, check_user_solution, solve_24


class SharedGameEngine(unittest.TestCase):
    def test_keyboard_and_display_operators(self):
        for expression in ('(3+3)*(5-1)', '(3+3)×(5-1)', '8/(3-8/3)', '8÷(3-8÷3)'):
            with self.subTest(expression=expression):
                self.assertEqual(evaluate(expression), (True, Fraction(24)))

    def test_reject_invalid_syntax_and_non_game_operators(self):
        for expression in ('2**3', '8//2', '2^3', '__import__("os")', '1/0',
                           '2(3)+4', '(2)3+4', '1 2+3', '()', '3+', '(3+4', '3.5*4', ''):
            with self.subTest(expression=expression):
                self.assertEqual(evaluate(expression), (False, None))

    def test_number_multiplicity_and_fraction_intermediates(self):
        self.assertTrue(check_user_solution([3, 3, 8, 8], '8/(3-8/3)')[0])
        self.assertFalse(check_user_solution([3, 3, 5, 1], '6*4')[0])
        self.assertFalse(check_user_solution([3, 3, 5, 1], '3+3+5+1')[0])

    def test_solver_answers_use_the_shared_evaluator(self):
        answers = solve_24([3, 3, 8, 8])
        self.assertTrue(answers)
        for answer in answers:
            self.assertEqual(evaluate(answer), (True, Fraction(24)))


if __name__ == '__main__':
    unittest.main()
