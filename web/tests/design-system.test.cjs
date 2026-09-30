const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..', '..');
const siteCss = readFileSync(path.join(root, 'web/src/styles/editorial.css'), 'utf8');
const docsCss = readFileSync(path.join(root, 'docs/stylesheets/extra.css'), 'utf8');
const mkdocs = readFileSync(path.join(root, 'mkdocs.yml'), 'utf8');

function tokens(css, selector) {
  const start = css.indexOf(`${selector} {`);
  assert.notEqual(start, -1, `${selector} exists`);
  const block = css.slice(start, css.indexOf('}', start));
  return Object.fromEntries([...block.matchAll(/(--[\w-]+):\s*(#[0-9a-f]{6});/gi)]
    .map(([, name, value]) => [name, value.toLowerCase()]));
}

test('daily site and documentation share light and dark design tokens', () => {
  const pairs = [
    [':root', ':root'],
    [':root[data-theme="dark"]', '[data-md-color-scheme="slate"]'],
  ];
  const names = {
    paper: 'background', surface: 'surface', ink: 'text', muted: 'muted',
    line: 'border', accent: 'accent',
  };
  for (const [siteSelector, docsSelector] of pairs) {
    const site = tokens(siteCss, siteSelector);
    const docs = tokens(docsCss, docsSelector);
    for (const [siteName, docsName] of Object.entries(names)) {
      assert.equal(site[`--desk-${siteName}`], docs[`--mi-${docsName}`]);
    }
  }
  assert.match(mkdocs, /scheme: default[\s\S]*Switch to dark mode/);
  assert.match(mkdocs, /scheme: slate[\s\S]*Switch to light mode/);
});
