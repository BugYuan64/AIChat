const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

function loadModel(withoutUrl = false) {
  const source = fs.readFileSync(path.resolve(__dirname, '../src/pages/login/model.ts'), 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const module = { exports: {} };
  new Function('module', 'exports', 'URL', output)(module, module.exports, withoutUrl ? undefined : URL);
  return module.exports;
}

test('auth form returns independent persistent errors for login and registration fields', () => {
  const { validateAuthForm } = loadModel();
  assert.deepEqual(validateAuthForm({ mode: 'login', handle: '', password: '', inviteCode: '', displayName: '' }), {
    handle: '请输入账号名',
    password: '请输入密码',
  });
  assert.deepEqual(validateAuthForm({ mode: 'register', handle: '  ', password: '', inviteCode: '', displayName: '' }), {
    inviteCode: '请输入邀请码',
    handle: '请设置账号名',
    displayName: '请输入昵称',
    password: '请设置密码',
  });
  assert.deepEqual(validateAuthForm({ mode: 'login', handle: 'demo', password: 'secret', inviteCode: '', displayName: '' }), {});
});

test('login copy separates login and registration title placeholder and autocomplete', () => {
  const { loginCopy } = loadModel();
  assert.deepEqual(loginCopy('login'), {
    title: '登录 AIChat',
    heading: '欢迎回来',
    accountPlaceholder: '请输入账号名',
    passwordAutocomplete: 'current-password',
  });
  assert.deepEqual(loginCopy('register'), {
    title: '邀请注册 AIChat',
    heading: '使用邀请加入',
    accountPlaceholder: '设置唯一账号名',
    passwordAutocomplete: 'new-password',
  });
});

test('server origin normalizes valid http and https origins', () => {
  const { normalizeServerOrigin } = loadModel();
  assert.equal(normalizeServerOrigin(' http://127.0.0.1:8000/ '), 'http://127.0.0.1:8000');
  assert.equal(normalizeServerOrigin('https://Chat.Example.com/'), 'https://chat.example.com');
});

test('server origin also works on runtimes without the browser URL constructor', () => {
  const { normalizeServerOrigin } = loadModel(true);
  assert.equal(normalizeServerOrigin('https://Chat.Example.com:443/'), 'https://chat.example.com');
  assert.equal(normalizeServerOrigin('http://[::1]:8000/'), 'http://[::1]:8000');
  assert.throws(() => normalizeServerOrigin('https://example.com:99999'), /格式/);
  assert.throws(() => normalizeServerOrigin('https:///example.com'), /主机/);
});

test('server origin explains empty scheme host credentials path query and hash failures', () => {
  const { normalizeServerOrigin } = loadModel();
  const cases = [
    ['', '请输入服务器地址'],
    ['chat.example.com', '请补充 http:// 或 https:// 协议'],
    ['https://', '服务器地址缺少主机名'],
    ['https://user:pass@example.com', '服务器地址不能包含用户名或密码'],
    ['https://example.com/v1', '服务器地址只能填写域名或 IP，不要包含路径'],
    ['https://example.com?mode=test', '服务器地址不能包含查询参数或片段'],
    ['https://example.com#top', '服务器地址不能包含查询参数或片段'],
  ];
  for (const [value, message] of cases) assert.throws(() => normalizeServerOrigin(value), new RegExp(message));
});
