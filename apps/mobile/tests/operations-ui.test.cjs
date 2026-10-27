const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
function model() { const m = { exports: {} }; new Function('module', 'exports', ts.transpileModule(fs.readFileSync(path.resolve(__dirname, '../src/ui/operations.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText)(m, m.exports); return m.exports; }
test('pairing approval requires verified code owned agent pending status and unexpired request', () => {
  const { canApprovePairing } = model();
  const input = { confirmed: true, agentId: 'owned', status: 'pending_user', expiresAt: '2026-10-27T12:00:00Z', now: Date.parse('2026-10-27T11:00:00Z') };
  assert.equal(canApprovePairing(input), true);
  for (const extra of [{ confirmed: false }, { agentId: '' }, { status: 'redeemed' }, { expiresAt: '2026-10-27T10:00:00Z' }, { expiresAt: 'invalid' }]) assert.equal(canApprovePairing({ ...input, ...extra }), false);
});
test('unknown run result stays warning and only run detail allows recovery retry', () => {
  const { runPresentation } = model();
  assert.equal(runPresentation('recovery_required').tone, 'warning');
  assert.equal(runPresentation('recovery_required').retryable, true);
  assert.equal(runPresentation('recovery_required').active, false);
  assert.equal(runPresentation('succeeded').tone, 'success');
  assert.equal(runPresentation('running').active, true);
  assert.equal(runPresentation('cancel_requested').active, false);
});
