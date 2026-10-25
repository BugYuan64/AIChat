const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { createPinia, setActivePinia } = require('pinia');

function runtime(respond, options = {}) {
  const storage = new Map([['aichat.access_token', 'access'], ['aichat.account', JSON.stringify({ account_id: 'me' })]]);
  for (const [key, value] of Object.entries(options.storage ?? {})) storage.set(key, value);
  const sockets = [];
  const uni = {
    getStorageSync: (key) => storage.get(key),
    setStorageSync: (key, value) => storage.set(key, value),
    removeStorageSync: (key) => storage.delete(key),
    request: (opts) => Promise.resolve().then(() => respond(opts)).then((data) => opts.success({ statusCode: 200, data: { request_id: 'req', data } })),
    connectSocket: () => {
      const handlers = {};
      const socket = { onOpen: (fn) => handlers.open = fn, onMessage: (fn) => handlers.message = fn,
        onClose: (fn) => handlers.close = fn, onError: () => {}, send: () => {}, close: () => {}, handlers };
      sockets.push(socket);
      return socket;
    },
  };
  const cache = new Map();
  function load(file) {
    const resolved = path.resolve(__dirname, '../src', file);
    if (cache.has(resolved)) return cache.get(resolved).exports;
    const module = { exports: {} };
    cache.set(resolved, module);
    const source = fs.readFileSync(resolved, 'utf8').replaceAll('import.meta.env', '(' + JSON.stringify(options.env ?? {}) + ')');
    const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
    const localRequire = (name) => name.startsWith('.') ? load(path.relative(path.resolve(__dirname, '../src'), path.resolve(path.dirname(resolved), name + '.ts'))) : require(name);
    vm.runInNewContext(js, { module, exports: module.exports, require: localRequire, uni, console, setTimeout, clearTimeout, setInterval, clearInterval }, { filename: resolved });
    return module.exports;
  }
  setActivePinia(createPinia());
  return { load, uni, sockets };
}
const tick = () => new Promise((resolve) => setImmediate(resolve));
const message = (id, seq) => ({ message_id: id, conversation_id: 'conv', seq, sender_account_id: 'other', kind: 'text', text: id, mentions: [], status: 'final', revision: '1', created_at: '2026-10-25T00:00:00Z', updated_at: '2026-10-25T00:00:00Z' });

test('server agent account_id remains usable in navigation and pairing', async () => {
  const rt = runtime(() => ({ items: [{ account_id: 'ai', handle: 'helper', display_name: 'Helper', owner_account_id: 'me', status: 'active', connector: { status: 'ready' } }] }));
  const result = await rt.load('api/agents.ts').listAgents();
  assert.equal(result.items[0].agent_id, 'ai');
  assert.equal(result.items[0].online, true);
});

test('flat contacts and incoming requests are both displayed', async () => {
  const rt = runtime((opts) => opts.url.endsWith('/contact-requests') ? { items: [{ request_id: 'request', status: 'pending', direction: 'incoming', account: { account_id: 'new', handle: 'new' } }] } : { items: [{ account_id: 'friend', handle: 'friend', kind: 'human' }] });
  const result = await rt.load('api/contacts.ts').listContacts();
  assert.equal(result.items[0].account.account_id, 'friend');
  assert.equal(result.items[0].relation, 'connected');
  assert.equal(result.items[1].relation, 'pending_incoming');
});

test('flat conversation members populate names and roles', async () => {
  const rt = runtime(() => ({ conversation_id: 'conv', kind: 'group', title: 'Group', status: 'active', members: [{ membership_id: 'membership', account_id: 'me', kind: 'human', handle: 'self', role: 'owner', joined_seq: '1' }] }));
  const store = rt.load('stores/chat.ts').useChatStore();
  await store.loadConversationDetail('conv');
  assert.equal(store.myRole.conv, 'owner');
  assert.equal(store.memberName('conv', 'me'), 'self');
});

test('background event does not suppress first history snapshot', async () => {
  const rt = runtime((opts) => opts.url.includes('/messages') ? { items: [message('old', '1'), message('new', '2')], has_more: true } : { conversation_id: 'conv', members: [] });
  const store = rt.load('stores/chat.ts').useChatStore();
  store.upsertMessage(message('new', '2'));
  await store.openConversation('conv');
  assert.deepEqual(Array.from(store.messages.conv, (m) => m.message_id), ['old', 'new']);
  assert.equal(store.hasMore.conv, true);
});

test('live event arriving during catchup cannot skip historical events', async () => {
  let resolvePage;
  const page = new Promise((resolve) => resolvePage = resolve);
  const rt = runtime((opts) => opts.url.includes('/events?') ? page : { ticket: 'ticket' });
  const store = rt.load('stores/chat.ts').useChatStore();
  store.setCursor('1');
  const events = rt.load('ws/events.ts');
  events.startEventsClient();
  await tick();
  const socket = rt.sockets[0];
  socket.handlers.message({ data: JSON.stringify({ type: 'welcome', current_cursor: '2' }) });
  socket.handlers.message({ data: JSON.stringify({ type: 'message.created', event_id: 'e3', cursor: '3', payload: message('live', '3') }) });
  resolvePage({ items: [{ type: 'message.created', event_id: 'e2', cursor: '2', payload: message('missed', '2') }], next_cursor: '2', has_more: false });
  await tick();
  events.stopEventsClient();
  assert.deepEqual(Array.from(store.messages.conv, (m) => m.message_id), ['missed', 'live']);
  assert.equal(store.cursor, '3');
});

test('logout during catchup cannot restore previous account messages or cursor', async () => {
  let resolvePage;
  const page = new Promise((resolve) => resolvePage = resolve);
  const rt = runtime(() => page);
  const store = rt.load('stores/chat.ts').useChatStore();
  store.setCursor('1');
  const events = rt.load('ws/events.ts');
  const syncing = events.catchUp();
  await tick();
  events.stopEventsClient();
  store.resetAll();
  resolvePage({ items: [{ type: 'message.created', event_id: 'old', cursor: '2', payload: message('private', '2') }], next_cursor: '2', has_more: false });
  await syncing;
  assert.equal(store.cursor, '');
  assert.equal(store.messages.conv, undefined);
});

test('grant revocation uses the server member-specific route', async () => {
  const rt = runtime((opts) => {
    assert.equal(opts.method, 'DELETE');
    assert.equal(opts.url, 'http://127.0.0.1:8000/v1/agents/ai/grants/person');
    return { revoked: true };
  });
  await rt.load('api/agents.ts').revokeGrant('ai', 'person');
});

test('configured API default preserves a user-configured custom server', () => {
  const rt = runtime(() => ({}), {
    env: { VITE_AICHAT_SERVER: 'https://api.aichat.wsnbb.shop' },
    storage: { 'aichat.server_base': 'https://personal.example' },
  });
  assert.equal(rt.load('api/client.ts').getServerBase(), 'https://personal.example');
});
