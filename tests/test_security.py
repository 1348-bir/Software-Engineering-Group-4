import io
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import test_group_integration as integration
from app import app
import group_site
import math_practice.engine as engine
import math_practice.routes as routes


class SecurityRegression(unittest.TestCase):
    setUp = integration.GroupIntegration.setUp
    tearDown = integration.GroupIntegration.tearDown

    def test_power_rejected_before_expensive_operation(self):
        with patch.object(engine.Fraction, '__pow__', side_effect=ValueError) as power:
            self.assertFalse(engine.solve('2^1000000000')[0])
            power.assert_not_called()
        self.assertEqual(engine.solve('2^10'), (True, 1024))
        self.assertFalse(engine.solve('9' * 100)[0])
        self.assertIsNone(engine.parse_user_answer('1e1000000000'))

    def test_answer_rejects_alternate_huge_exponent_spelling(self):
        with patch.object(engine, 'Fraction', side_effect=ValueError) as fraction:
            self.assertIsNone(engine.parse_user_answer('1e1_000_000_000'))
            fraction.assert_not_called()
        self.assertEqual(engine.parse_user_answer('1.5e2'), 150)
        self.assertEqual(engine.parse_user_answer('2 1/2'), engine.Fraction(5, 2))

    def test_expression_limits_preserve_normal_grading(self):
        self.assertFalse(engine.solve('2^12^12')[0])
        self.assertFalse(engine.solve('(9999999999999999^12)^12')[0])
        self.assertFalse(engine.solve('1+' * 300 + '1')[0])
        self.assertEqual(engine.grade_one('6 ÷ 4', '3/2')[:2], (True, '3/2'))
        self.assertFalse(engine.evaluate('2^13')[0])

    def test_generation_stops_at_deadline(self):
        with patch.object(engine.time, 'monotonic', side_effect=[0, 6]):
            self.assertEqual(engine.generate_to_db(routes.db, count=3, batch=3), 0)
        self.assertEqual(routes.db.question_count(), 0)

    def test_public_generation_has_default_deadline(self):
        with patch.object(engine.time, 'monotonic', side_effect=[0, 3]):
            self.assertEqual(engine.generate_batch(200,
                cfg=engine.QuestionConfig(num_range=1, allow_parentheses=True)), [])

    def test_submit_rejects_unbounded_batch(self):
        response = self.client.post('/math/api/submit', json={
            'items': [{'expr': '1+1', 'answer': '2'}] * 201})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(routes.db.accuracy()['total'], 0)

    def test_generate_requires_admin_and_valid_limits(self):
        with patch.dict(app.config, STUDIO_ADMIN_TOKEN='audit-admin'):
            self.assertEqual(self.client.post('/math/api/generate', json={'count': 1}).status_code, 403)
            self.assertEqual(self.client.post('/math/api/generate', json={'count': 1},
                headers={'Authorization': 'Bearer wrong-token'}).status_code, 403)
            for data in ({'count': 1000000000}, {'count': 1, 'batch': 0},
                         {'count': 1, 'batch': -1}, {'count': 'bad'}, []):
                with self.subTest(data=data), patch.object(routes, 'generate_to_db', return_value=0) as generate:
                    response = self.client.post('/math/api/generate', json=data,
                        headers={'Authorization': 'Bearer audit-admin'})
                    self.assertEqual(response.status_code, 400)
                    generate.assert_not_called()
            response = self.client.post('/math/api/generate', json={'count': 3, 'batch': 3},
                headers={'Authorization': 'Bearer audit-admin'})
            self.assertEqual(response.status_code, 200)
            self.assertGreater(routes.db.question_count(), 0)
        with patch.dict(app.config, STUDIO_ADMIN_TOKEN=''):
            self.assertEqual(self.client.post('/math/api/generate', json={'count': 1},
                headers={'Authorization': 'Bearer audit-admin'}).status_code, 403)

    def test_avatar_requires_admin_and_csrf(self):
        def upload(token='', csrf=''):
            return self.client.post('/avatar/upload', data={'member_id': 'xu-jingxuan',
                'admin_token': token, 'csrf_token': csrf,
                'avatar': (io.BytesIO(b'GIF89a-audit'), 'a.gif')})
        with patch.dict(app.config, STUDIO_ADMIN_TOKEN='audit-admin'):
            self.assertEqual(upload().status_code, 403)
            self.assertEqual(upload('wrong-admin').status_code, 403)
            self.assertEqual(upload('audit-admin').status_code, 403)
            page = self.client.get('/members/xu-jingxuan').get_data(as_text=True)
            token = re.search(r'name="csrf_token" value="([^"]+)"', page)
            self.assertIsNotNone(token)
            self.assertEqual(upload('audit-admin', 'wrong-csrf').status_code, 403)
            self.assertFalse(group_site.AVATAR_DIR.exists())
            self.assertIn('avatar_ok=1', upload('audit-admin', token[1]).location)
            self.assertEqual(len(list(group_site.AVATAR_DIR.glob('*'))), 1)
        with patch.dict(app.config, STUDIO_ADMIN_TOKEN=''):
            self.assertEqual(upload('audit-admin', 'anything').status_code, 403)

    def test_legacy_profile_has_authorized_avatar_form(self):
        page = self.client.get('/members/wen-jingxiong/original-profile').get_data(as_text=True)
        self.assertRegex(page, r'name="csrf_token" value="[^\"]+"')
        self.assertIn('name="admin_token"', page)

    @unittest.skipUnless(shutil.which('node'), 'Node.js required for DOM regression')
    def test_history_polling_renders_untrusted_fields_as_text(self):
        payload = '<img src=x onerror="throw 1">'
        runner = r'''
const vm = require('node:vm');
const assert = require('node:assert/strict');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
class Element {
  constructor() { this.children = []; this.style = {}; this.textContent = ''; }
  set innerHTML(value) { if (value) throw Error('unsafe HTML sink'); this.children = []; }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.append(node); }
  insertBefore(node) { this.children.unshift(node); }
  querySelector() { return null; }
}
const elements = new Map();
const document = {createElement: () => new Element(), getElementById: id => {
  if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id);
}};
const context = vm.createContext({document, console, setInterval() {},
  fetch: async () => ({json: async () => input.data})});
vm.runInContext(input.helper + '\n' + input.script, context);
(async () => {
  await vm.runInContext('pollHistory()', context);
  const rows = document.getElementById('historyBody').children;
  assert.equal(rows.length, 1);
  assert.ok(rows[0].children.some(cell => cell.textContent === input.payload));
})().catch(e => {console.error(e); process.exitCode = 1;});
'''
        for url, row in (
            ('/math/history', dict(expr=payload, user_answer=payload, standard=payload)),
            ('/game24/history', dict(nums=payload, user_expr=payload, reason=payload)),
        ):
            with self.subTest(url=url):
                html = self.client.get(url).get_data(as_text=True)
                script = next(s for s in re.findall(r'<script>(.*?)</script>', html, re.S) if 'pollHistory' in s)
                helper_path = Path(app.root_path) / 'static' / 'history.js'
                result = subprocess.run(['node', '-e', runner], input=json.dumps({
                    'script': script, 'helper': helper_path.read_text() if helper_path.exists() else '',
                    'payload': payload, 'data': {'attempts': [dict(id=1, is_correct=0, created_at='', **row)],
                        'latest_id': 1, 'stats': {'total': 1, 'correct': 0, 'accuracy': 0}}}),
                    text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
