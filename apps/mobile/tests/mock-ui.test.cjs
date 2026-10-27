const { test } = require('node:test');
const assert = require('node:assert/strict');
test('UI mock supports real write response shapes and rejects unknown routes', async () => {
  const { createMockServer } = await import('../scripts/mock-server.mjs');
  const server = createMockServer();
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const base = 'http://127.0.0.1:' + server.address().port;
  try {
    assert.equal((await fetch(base + '/v1/not-implemented')).status, 404);
    const login = await (await fetch(base + '/v1/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ handle: 'demo', password: 'demo-password' }) })).json();
    assert.ok(login.data.access_token);
    const sent = await (await fetch(base + '/v1/conversations/conv_group/messages', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: '测试消息', client_message_id: 'test-id' }) })).json();
    assert.equal(sent.data.message.text, '测试消息');
    assert.ok(sent.data.message.message_id);
    const pairing = await (await fetch(base + '/v1/pairings/demo?code=demo')).json();
    assert.equal(pairing.data.status, 'pending_user');
  } finally { await new Promise((resolve) => server.close(resolve)); }
});
