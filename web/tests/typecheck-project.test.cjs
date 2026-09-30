const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

test('typecheck project includes authored code but not generated browser bundles', () => {
  const root = path.resolve(__dirname, '..');
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'quant-typecheck-'));
  try {
    const config = JSON.parse(fs.readFileSync(path.join(root, 'tsconfig.json'), 'utf8'));
    config.extends = path.join(root, 'node_modules/astro/tsconfigs/strict.json');
    config.include = ['src/**/*', 'dist/**/*'];
    fs.mkdirSync(path.join(fixture, 'src'));
    fs.mkdirSync(path.join(fixture, 'dist'));
    fs.writeFileSync(path.join(fixture, 'src/probe.ts'), 'export const probe = 1;');
    fs.writeFileSync(path.join(fixture, 'dist/bundle.js'), 'const generated = 1;');
    fs.writeFileSync(path.join(fixture, 'tsconfig.json'), JSON.stringify(config));
    const resolved = JSON.parse(execFileSync(process.execPath, [
      path.join(root, 'node_modules/typescript/bin/tsc'), '--showConfig', '--project', path.join(fixture, 'tsconfig.json'),
    ], { encoding: 'utf8' }));
    assert.ok(resolved.files.includes('./src/probe.ts'));
    assert.ok(!resolved.files.includes('./dist/bundle.js'));
  } finally {
    fs.rmSync(fixture, { recursive: true });
  }
});
