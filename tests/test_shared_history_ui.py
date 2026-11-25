import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which('node'), 'Node.js required for polling regression')
class SharedHistoryUI(unittest.TestCase):
    def test_polling_cursor_rows_stats_overlap_and_retry(self):
        helper = Path(__file__).resolve().parents[1] / 'static' / 'history.js'
        runner = r'''
const assert = require('node:assert/strict');
class Element {
  constructor() { this.children = []; this.style = {}; }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return this.text; }
  appendChild(node) { this.children.push(node); }
  insertBefore(node) { this.children.unshift(node); }
  querySelector() { return this.empty ? {} : null; }
}
const elements = {};
global.document = {createElement: () => new Element(),
  getElementById: id => elements[id] ||= new Element()};
const body = document.getElementById('historyBody');
body.empty = true;
body.children.push({placeholder: true});
let release, calls = [], failure = false;
global.fetch = url => {
  calls.push(url);
  if (failure) return Promise.reject(Error('offline'));
  return new Promise(resolve => { release = data => resolve({json: async () => data}); });
};
const errors = [];
console.error = (...args) => errors.push(args);
const poll = createHistoryPoller({url: '/history', latestId: 3,
  renderRow: (row, a) => appendHistoryCell(row, a.value),
  stats: {statTotal: s => s.total, statAcc: s => (s.accuracy * 100).toFixed(1) + '%'}});
(async () => {
  const pending = poll();
  await poll();
  assert.equal(calls.length, 1);
  release({attempts: [{id: 4, value: '<img onerror=bad>'}, {id: 5, value: 'new'}],
    latest_id: 5, stats: {total: 5, accuracy: .25}});
  await pending;
  assert.deepEqual(body.children.map(row => row.children[0].textContent), ['new', '<img onerror=bad>']);
  assert.equal(elements.statTotal.textContent, '5');
  assert.equal(elements.statAcc.textContent, '25.0%');
  failure = true;
  await poll();
  assert.equal(errors.length, 1);
  failure = false;
  const retry = poll();
  assert.equal(calls[2], '/history?after=5');
  release({attempts: [], latest_id: 5, stats: {total: 6, accuracy: .5}});
  await retry;
  assert.equal(body.children.length, 2);
  assert.equal(elements.statTotal.textContent, '6');
})().catch(error => { process.stderr.write(String(error)); process.exitCode = 1; });
'''
        result = subprocess.run(['node', '-e', helper.read_text(encoding='utf-8') + runner],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
