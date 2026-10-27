const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
function model() { const m = { exports: {} }; new Function('module', 'exports', ts.transpileModule(fs.readFileSync(path.resolve(__dirname, '../src/ui/chat.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText)(m, m.exports); return m.exports; }
test('chat Enter sends only unmodified non-composing Enter', () => {
  const { shouldSendOnEnter } = model();
  assert.equal(shouldSendOnEnter({ key: 'Enter' }), true);
  for (const extra of [{ shiftKey: true }, { isComposing: true }, { keyCode: 229 }, { ctrlKey: true }, { altKey: true }, { metaKey: true }]) assert.equal(shouldSendOnEnter({ key: 'Enter', ...extra }), false);
  assert.equal(shouldSendOnEnter({ key: 'a' }), false);
});
test('conversation filter matches title and handle without changing the source order', () => {
  const { filterConversations } = model();
  const rows = [{ conversation_id: '1', title: '项目讨论' }, { conversation_id: '2', title: 'Helper', direct_peer: { handle: 'ASSIST' } }];
  assert.deepEqual(filterConversations(rows, '项目'), [rows[0]]);
  assert.deepEqual(filterConversations(rows, ' assist '), [rows[1]]);
  assert.deepEqual(filterConversations(rows, ''), rows);
});
test('chat follows new messages only while the reader remains near the bottom', () => {
  const { isNearMessageBottom } = model();
  assert.equal(isNearMessageBottom(490, 1000, 500), true);
  assert.equal(isNearMessageBottom(100, 1000, 500), false);
  assert.equal(isNearMessageBottom(0, 200, 500), true);
});
