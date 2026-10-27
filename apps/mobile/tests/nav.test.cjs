const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

/**
 * nav.ts 的 goBack 三条分支：
 * - 页面栈有上一页 → navigateBack；
 * - 深链直达（栈只有 1 层）且兜底是 tabBar 页 → switchTab；
 * - 深链直达且兜底是普通页 → redirectTo（替换当前页，不在栈里堆重复详情页）。
 */
function loadNav() {
  const module = { exports: {} };
  const calls = [];
  const pages = [];
  const uni = {
    navigateBack: (opts) => calls.push({ api: 'navigateBack', url: opts?.url ?? '' }),
    switchTab: (opts) => calls.push({ api: 'switchTab', url: opts.url }),
    redirectTo: (opts) => calls.push({ api: 'redirectTo', url: opts.url }),
  };
  const getCurrentPages = () => pages;
  const source = fs.readFileSync(path.resolve(__dirname, '../src/utils/nav.ts'), 'utf8');
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  new Function('module', 'exports', 'uni', 'getCurrentPages', js)(module, module.exports, uni, getCurrentPages);
  return { goBack: module.exports.goBack, calls, pages };
}

test('goBack walks the stack when there is a previous page', () => {
  const { goBack, calls, pages } = loadNav();
  pages.push({ route: 'pages/sessions/sessions' }, { route: 'pages/agents/detail' });
  goBack({ url: '/pages/agents/agents' });
  assert.equal(JSON.stringify(calls), JSON.stringify([{ api: 'navigateBack', url: '' }]));
});

test('goBack falls back to switchTab for tabBar owners on deep links', () => {
  const { goBack, calls, pages } = loadNav();
  pages.push({ route: 'pages/pairing/scan' });
  goBack({ url: '/pages/me/me', tab: true });
  assert.equal(JSON.stringify(calls), JSON.stringify([{ api: 'switchTab', url: '/pages/me/me' }]));
});

test('goBack redirects to the owning list for plain pages on deep links', () => {
  const { goBack, calls, pages } = loadNav();
  pages.push({ route: 'pages/agents/detail' });
  goBack({ url: '/pages/agents/agents' });
  assert.equal(JSON.stringify(calls), JSON.stringify([{ api: 'redirectTo', url: '/pages/agents/agents' }]));
});
