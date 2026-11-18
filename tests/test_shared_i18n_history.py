import importlib
import unittest
from unittest.mock import patch

from flask import Flask, request


class SharedTranslations(unittest.TestCase):
    def test_language_selection_and_translation_contract(self):
        app = Flask(__name__)
        for name in ('math_practice', 'game_24', 'dice_game'):
            module = importlib.import_module(name + '.i18n')
            for query, header, expected in (
                ('?lang=ja', 'zh', 'ja'), ('?lang=xx', 'ja,zh', 'zh'),
                ('', 'ja', 'ja'), ('', 'fr', 'en'),
            ):
                with self.subTest(module=name, query=query, header=header):
                    with app.test_request_context('/' + query, headers={'Accept-Language': header}):
                        self.assertEqual(module.get_lang(request), expected)
            with patch.dict(module.TRANSLATIONS, {'zh': {'sample': '你好 {name}'}, 'en': {}}):
                self.assertEqual(module.t('sample', 'xx', name='A'), '你好 A')
                self.assertEqual(module.t('sample', 'en'), 'sample')
                self.assertEqual(module.t('sample', name='A'), '你好 A')
                self.assertEqual(module.translator('zh')('sample', other='A'), '你好 {name}')
                self.assertEqual(module.t('missing'), 'missing')


class SharedHistory(unittest.TestCase):
    def test_history_filter_stats_empty_and_invalid_cursor(self):
        app = Flask(__name__)
        for name, stat_name in (('math_practice', 'accuracy'), ('game_24', 'accuracy'), ('dice_game', 'stats')):
            module = importlib.import_module(name + '.routes')
            with patch.object(module, 'current_user', return_value='user-1'), \
                    patch.object(module.db, 'recent_attempts', return_value=[{'id': 9}, {'id': 4}]) as recent, \
                    patch.object(module.db, stat_name, return_value={'total': 2}) as stats:
                with app.test_request_context('/?after=4'):
                    self.assertEqual(module.api_history().get_json(), {
                        'attempts': [{'id': 9}], 'stats': {'total': 2}, 'latest_id': 9})
                recent.assert_called_once_with('user-1', limit=50)
                stats.assert_called_once_with('user-1')
                recent.return_value = []
                with app.test_request_context('/?after=12'):
                    self.assertEqual(module.api_history().get_json()['latest_id'], 12)
                recent.reset_mock()
                stats.reset_mock()
                for cursor in ('bad', '', '1.2'):
                    with self.subTest(module=name, cursor=cursor), app.test_request_context('/?after=' + cursor):
                        response, status = module.api_history()
                        self.assertEqual(status, 400)
                        self.assertIn('error', response.get_json())
                recent.assert_not_called()
                stats.assert_not_called()
