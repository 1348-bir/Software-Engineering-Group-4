import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app
import group_site
import math_practice.routes as math_routes
import game_24.routes as game_routes
import dice_game.routes as dice_routes
from math_practice.db import MathDB
from game_24.db import Game24DB
from dice_game.db import DiceDB
from math_practice.engine import QuestionConfig, generate_batch, solve


class GroupIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='group-site-test-')
        root = Path(self.temp.name)
        self.original_dbs = (math_routes.db, game_routes.db, dice_routes.db)
        math_routes.db = MathDB(str(root / 'math.db'))
        game_routes.db = Game24DB(str(root / 'game.db'))
        dice_routes.db = DiceDB(str(root / 'dice.db'))
        self.avatars = patch('group_site.AVATAR_DIR', root / 'avatars')
        self.avatars.start()
        app.config.update(TESTING=True, SECRET_KEY='integration-test-only')
        self.client = app.test_client()

    def tearDown(self):
        math_routes.db, game_routes.db, dice_routes.db = self.original_dbs
        self.avatars.stop()
        self.temp.cleanup()

    def test_team_and_member_profiles(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        for name in ('徐敬轩', '文敬雄', '软件工程第四小组'):
            self.assertIn(name, response.get_data(as_text=True))
        self.assertEqual(self.client.get('/members').status_code, 200)
        for slug in ('xu-jingxuan', 'wen-jingxiong'):
            self.assertEqual(self.client.get('/members/' + slug).status_code, 200)
        self.assertEqual(self.client.get('/members/unknown').status_code, 404)
        self.assertEqual(self.client.get('/profile').location, '/members')

    def test_all_integrated_pages(self):
        pages = ['/projects', '/math/', '/math/history', '/math/print?count=8&columns=2&show_answers=1', '/math/upload', '/game24/', '/game24/history', '/dice/', '/dice/history', '/members/wen-jingxiong/original-profile']
        for url in pages:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertIn('软件工程第四小组', response.get_data(as_text=True))

    def test_old_counter_links_and_post(self):
        self.assertEqual(self.client.get('/projects/code-counter').location, '/code-stats')
        self.assertIn('/code-stats#url-title', self.client.get('/projects/github-counter').location)
        response = self.client.post('/projects/code-counter', data={'file': (io.BytesIO(b'# c\nx=1\n'), 'a.py')})
        self.assertEqual(response.status_code, 200)
        self.assertIn('"files": 1', response.get_data(as_text=True))
        self.assertEqual(self.client.post('/projects/code-counter').status_code, 400)

    def test_legacy_github_post_uses_new_analyzer(self):
        fixture = {'totals': {'files': 1}, 'files': [], 'skipped': [], 'languages': []}
        for value in ('owner/repo', 'git@github.com:owner/repo.git'):
            with self.subTest(value=value), patch('group_site.analyze_url', return_value=fixture) as analyze:
                self.assertEqual(self.client.post('/projects/github-counter', data={'repo_url': value}).status_code, 200)
                analyze.assert_called_once_with('https://github.com/owner/repo')

    def test_custom_math_questions_grading_and_history(self):
        response = self.client.get('/math/api/questions?count=6&num_range=30&allow_mult_div=1&allow_parentheses=1')
        self.assertEqual(response.status_code, 200)
        questions = response.json['questions']
        self.assertEqual(len(questions), 6)
        self.assertTrue(all(solve(q['expr'])[0] for q in questions))
        submitted = self.client.post('/math/api/submit', json={'items': [{'expr': '3 + 5', 'answer': '8'}, {'expr': '6 ÷ 4', 'answer': '3/2'}]})
        self.assertEqual((submitted.json['correct'], submitted.json['total']), (2, 2))
        self.assertEqual(self.client.get('/math/api/history').json['stats']['total'], 2)
        self.assertEqual(app.test_client().get('/math/api/history').json['stats']['total'], 0)

    def test_fraction_and_negative_configuration(self):
        cfg = QuestionConfig(count=8, num_range=20, allow_mult_div=True, allow_parentheses=True, allow_fraction=True, allow_negative=True)
        self.assertEqual(len(generate_batch(8, cfg)), 8)

    def test_question_bank_generation(self):
        with patch.dict(app.config, STUDIO_ADMIN_TOKEN='integration-admin'):
            response = self.client.post('/math/api/generate', json={'count': 5, 'batch': 5},
                headers={'Authorization': 'Bearer integration-admin'})
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json['total_in_db'], 1)
        self.assertEqual(len(self.client.get('/math/api/questions?count=3').json['questions']), 3)

    def test_original_game24_and_history(self):
        self.assertEqual(len(self.client.get('/game24/api/puzzle').json['nums']), 4)
        response = self.client.post('/game24/api/submit', json={'nums': [3, 3, 5, 1], 'expr': '(3+3)×(5-1)'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['correct'])
        self.assertTrue(response.json['standard_answers'])
        self.assertEqual(self.client.get('/game24/api/history').json['stats']['total'], 1)

    def test_dice_and_isolated_history(self):
        with patch('dice_game.routes.roll_dice', return_value=(3, 4)):
            response = self.client.post('/dice/api/roll')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['total'], 7)
        self.assertTrue(response.json['win'])
        self.assertEqual(len(self.client.get('/dice/api/history').json['attempts']), 1)
        self.assertEqual(len(app.test_client().get('/dice/api/history').json['attempts']), 0)

    def test_optional_ocr_fallback(self):
        with patch('math_practice.ocr.recognize', return_value=''):
            response = self.client.post('/math/api/ocr', data={'image': (io.BytesIO(b'image'), 'a.png')})
        self.assertEqual(response.status_code, 200)
        self.assertIn('error', response.json)

    def test_member_avatar_isolation(self):
        admin = patch.dict(app.config, STUDIO_ADMIN_TOKEN='integration-admin')
        admin.start()
        self.addCleanup(admin.stop)
        with self.client.session_transaction() as session:
            session['csrf_token'] = 'integration-csrf'
        credentials = {'admin_token': 'integration-admin', 'csrf_token': 'integration-csrf'}
        image = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jF9kAAAAASUVORK5CYII=')
        for slug in ('xu-jingxuan', 'wen-jingxiong'):
            response = self.client.post('/avatar/upload', data={**credentials, 'member_id': slug, 'avatar': (io.BytesIO(image), 'a.png')})
            self.assertIn('avatar_ok=1', response.location)
        self.assertEqual(len(list(group_site.AVATAR_DIR.glob('xu-jingxuan-*'))), 1)
        self.assertEqual(len(list(group_site.AVATAR_DIR.glob('wen-jingxiong-*'))), 1)
        self.client.post('/avatar/upload', data={**credentials, 'member_id': 'xu-jingxuan', 'avatar': (io.BytesIO(image), 'new.png')})
        self.assertEqual(len(list(group_site.AVATAR_DIR.glob('xu-jingxuan-*'))), 1)
        self.assertEqual(len(list(group_site.AVATAR_DIR.glob('wen-jingxiong-*'))), 1)
        response = self.client.post('/avatar/upload', data={**credentials, 'member_id': 'xu-jingxuan', 'avatar': (io.BytesIO(b'not image'), 'a.png')})
        self.assertIn('avatar_error=format', response.location)


if __name__ == '__main__':
    unittest.main()
