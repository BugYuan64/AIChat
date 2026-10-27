const { test } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const ts = require('typescript');

const mobileRoot = path.resolve(__dirname, '..');

function loadTs(relativePath) {
  const source = fs.readFileSync(path.join(mobileRoot, relativePath), 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const module = { exports: {} };
  new Function('module', 'exports', 'require', output)(module, module.exports, require);
  return module.exports;
}

function runIconGenerator() {
  const npmCli = process.env.npm_execpath
    || path.join(path.dirname(process.execPath), 'node_modules', 'npm', 'bin', 'npm-cli.js');
  const result = spawnSync(process.execPath, [npmCli, 'run', 'icons:generate'], {
    cwd: mobileRoot,
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
}

function digest(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

test('layout mode changes only at the approved compact and desktop breakpoints', () => {
  const { layoutMode, isDesktopWidth } = loadTs('src/ui/layout.ts');
  assert.equal(layoutMode(767), 'mobile');
  assert.equal(layoutMode(768), 'compact');
  assert.equal(layoutMode(899), 'compact');
  assert.equal(layoutMode(900), 'desktop');
  assert.equal(layoutMode(1099), 'desktop');
  assert.equal(layoutMode(1100), 'desktop');
  assert.equal(isDesktopWidth(899), false);
  assert.equal(isDesktopWidth(900), true);
});

test('icon generation is local, valid PNG, and byte deterministic', () => {
  runIconGenerator();
  const files = [
    'src/static/icons/default/message-circle.png',
    'src/static/icons/primary/send.png',
    'src/static/icons/success/circle-check.png',
    'src/static/icons/danger/circle-alert.png',
    'src/static/tab/chat.png',
    'src/static/tab/chat-active.png',
  ].map((file) => path.join(mobileRoot, file));

  const first = files.map((file) => {
    assert.equal(fs.readFileSync(file).subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
    return digest(file);
  });
  runIconGenerator();
  assert.deepEqual(files.map(digest), first);
});

test('icon catalog rejects unknown icon names instead of silently breaking the UI', () => {
  const { iconSource } = loadTs('src/ui/icons.ts');
  assert.throws(() => iconSource('not-a-real-icon'), /Unknown UI icon/);
});
