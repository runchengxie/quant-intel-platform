const test = require('node:test');
const assert = require('node:assert/strict');

function fakeSvg(height = '600') {
  return {
    getAttribute: (key) => ({ width: '960', height })[key],
    cloneNode: () => ({ style: { setProperty() {} } }),
  };
}

test('PNG export rasterizes the displayed SVG at 2x and releases object URLs', async () => {
  const { downloadMarketChartPng } = await import('../src/lib/market-chart-download.ts');
  const previous = {
    Image: globalThis.Image,
    XMLSerializer: globalThis.XMLSerializer,
    document: globalThis.document,
    createObjectURL: URL.createObjectURL,
    revokeObjectURL: URL.revokeObjectURL,
    setTimeout: globalThis.setTimeout,
    getComputedStyle: globalThis.getComputedStyle,
  };
  const revoked = [];
  const clicked = [];
  const canvas = {
    getContext: () => ({ scale: (...args) => clicked.push(['scale', ...args]), drawImage: (...args) => clicked.push(['draw', ...args]) }),
    toBlob: (callback, type) => callback(new Blob(['png'], { type })),
  };
  try {
    globalThis.XMLSerializer = class { serializeToString() { return '<svg width="960" height="600"/>'; } };
    globalThis.getComputedStyle = () => ({ getPropertyValue: () => '' });
    globalThis.Image = class {
      set src(value) { this.currentSrc = value; queueMicrotask(() => this.onload()); }
    };
    globalThis.document = {
      body: { append: (node) => clicked.push(['append', node]) },
      createElement: (tag) => tag === 'canvas' ? canvas : {
        click() { clicked.push(['click', this.download]); }, remove() {},
      },
    };
    URL.createObjectURL = (blob) => `blob:test-${blob.type}`;
    URL.revokeObjectURL = (url) => revoked.push(url);
    globalThis.setTimeout = (callback) => callback();
    await downloadMarketChartPng(fakeSvg(), '2026-09-25');
    assert.equal(canvas.width, 1920);
    assert.equal(canvas.height, 1200);
    assert.ok(clicked.some((row) => row[0] === 'draw'));
    assert.ok(clicked.some((row) => row[0] === 'scale' && row[1] === 2 && row[2] === 2));
    assert.ok(clicked.some((row) => row[0] === 'click' && row[1] === '2026-09-25-market-daily-report.png'));
    await downloadMarketChartPng(fakeSvg('6000'), '2026-09-25', 'asia-daily');
    assert.ok(clicked.some((row) => row[0] === 'click' && row[1] === '2026-09-25-asia-daily-report.png'));
    assert.ok(canvas.height <= 8192);
    assert.ok(canvas.width * canvas.height <= 12_000_000);
    assert.deepEqual(revoked, ['blob:test-image/png', 'blob:test-image/svg+xml;charset=utf-8',
      'blob:test-image/png', 'blob:test-image/svg+xml;charset=utf-8']);
  } finally {
    globalThis.Image = previous.Image;
    globalThis.XMLSerializer = previous.XMLSerializer;
    globalThis.document = previous.document;
    URL.createObjectURL = previous.createObjectURL;
    URL.revokeObjectURL = previous.revokeObjectURL;
    globalThis.setTimeout = previous.setTimeout;
    globalThis.getComputedStyle = previous.getComputedStyle;
  }
});

test('PNG export removes the download link and releases URLs if the browser blocks the click', async () => {
  const { downloadMarketChartPng } = await import('../src/lib/market-chart-download.ts');
  const previous = {
    Image: globalThis.Image,
    XMLSerializer: globalThis.XMLSerializer,
    document: globalThis.document,
    createObjectURL: URL.createObjectURL,
    revokeObjectURL: URL.revokeObjectURL,
    setTimeout: globalThis.setTimeout,
    getComputedStyle: globalThis.getComputedStyle,
  };
  const revoked = [];
  let removed = false;
  try {
    globalThis.XMLSerializer = class { serializeToString() { return '<svg width="960" height="600"/>'; } };
    globalThis.getComputedStyle = () => ({ getPropertyValue: () => '' });
    globalThis.Image = class { set src(value) { this.currentSrc = value; queueMicrotask(() => this.onload()); } };
    globalThis.document = {
      body: { append() {} },
      createElement: (tag) => tag === 'canvas' ? {
        getContext: () => ({ scale() {}, drawImage() {} }),
        toBlob: (callback) => callback(new Blob(['png'], { type: 'image/png' })),
      } : {
        click() { throw new Error('download blocked'); },
        remove() { removed = true; },
      },
    };
    URL.createObjectURL = (blob) => `blob:test-${blob.type}`;
    URL.revokeObjectURL = (url) => revoked.push(url);
    globalThis.setTimeout = (callback) => callback();
    await assert.rejects(downloadMarketChartPng(fakeSvg(), '2026-09-25'), /download blocked/);
    assert.equal(removed, true);
    assert.deepEqual(revoked, ['blob:test-image/png', 'blob:test-image/svg+xml;charset=utf-8']);
  } finally {
    globalThis.Image = previous.Image;
    globalThis.XMLSerializer = previous.XMLSerializer;
    globalThis.document = previous.document;
    URL.createObjectURL = previous.createObjectURL;
    URL.revokeObjectURL = previous.revokeObjectURL;
    globalThis.setTimeout = previous.setTimeout;
    globalThis.getComputedStyle = previous.getComputedStyle;
  }
});

test('PNG export serializes the active dark theme on a clone and keeps blank values on SVG fallbacks', async () => {
  const { downloadMarketChartPng } = await import('../src/lib/market-chart-download.ts');
  const previous = {
    Image: globalThis.Image,
    XMLSerializer: globalThis.XMLSerializer,
    document: globalThis.document,
    getComputedStyle: globalThis.getComputedStyle,
    createObjectURL: URL.createObjectURL,
    revokeObjectURL: URL.revokeObjectURL,
    setTimeout: globalThis.setTimeout,
  };
  const originalStyle = new Map([['--report-bg', '#original']]);
  const cloneStyle = new Map();
  let cloned = false;
  const svg = {
    getAttribute: (key) => ({ width: '960', height: '600' })[key],
    style: { getPropertyValue: (name) => originalStyle.get(name) ?? '' },
    cloneNode(deep) {
      assert.equal(deep, true);
      cloned = true;
      return { style: { setProperty: (name, value) => cloneStyle.set(name, value) } };
    },
  };
  const blobs = [];
  try {
    globalThis.getComputedStyle = (target) => {
      assert.equal(target, svg);
      return { getPropertyValue: (name) => ({
        '--report-bg': ' #1b2128 ',
        '--report-ink': ' #e8edf2 ',
        '--report-muted': ' #9aa4ae ',
        '--report-track': '  ',
        '--report-line': '',
      })[name] ?? '' };
    };
    globalThis.XMLSerializer = class {
      serializeToString(target) {
        const style = target === svg ? originalStyle : cloneStyle;
        const inline = [...style].map(([name, value]) => `${name}:${value}`).join(';');
        return `<svg style="${inline}"><rect fill="var(--report-bg, #fff9f2)"/><text fill="var(--report-ink, #29251f)"/></svg>`;
      }
    };
    globalThis.Image = class { set src(value) { queueMicrotask(() => this.onload()); } };
    globalThis.document = {
      body: { append() {} },
      createElement: (tag) => tag === 'canvas' ? {
        getContext: () => ({ scale() {}, drawImage() {} }),
        toBlob: (callback) => callback(new Blob(['png'], { type: 'image/png' })),
      } : { click() {}, remove() {} },
    };
    URL.createObjectURL = (blob) => { blobs.push(blob); return `blob:test-${blobs.length}`; };
    URL.revokeObjectURL = () => {};
    globalThis.setTimeout = (callback) => callback();
    await downloadMarketChartPng(svg, '2026-09-25');
    const markup = await blobs[0].text();
    assert.match(markup, /--report-bg:#1b2128/);
    assert.match(markup, /--report-ink:#e8edf2/);
    assert.match(markup, /--report-muted:#9aa4ae/);
    assert.doesNotMatch(markup, /--report-track:/);
    assert.doesNotMatch(markup, /--report-line:/);
    assert.match(markup, /var\(--report-bg, #fff9f2\)/);
    assert.equal(svg.style.getPropertyValue('--report-bg'), '#original');
    assert.equal(originalStyle.size, 1);
    assert.equal(cloned, true);
    cloneStyle.clear();
    originalStyle.clear();
    globalThis.getComputedStyle = undefined;
    await downloadMarketChartPng(svg, '2026-09-25');
    const fallbackMarkup = await blobs[2].text();
    assert.doesNotMatch(fallbackMarkup, /--report-bg:/);
    assert.match(fallbackMarkup, /var\(--report-bg, #fff9f2\)/);
    assert.match(fallbackMarkup, /var\(--report-ink, #29251f\)/);
  } finally {
    globalThis.Image = previous.Image;
    globalThis.XMLSerializer = previous.XMLSerializer;
    globalThis.document = previous.document;
    globalThis.getComputedStyle = previous.getComputedStyle;
    URL.createObjectURL = previous.createObjectURL;
    URL.revokeObjectURL = previous.revokeObjectURL;
    globalThis.setTimeout = previous.setTimeout;
  }
});

test('PNG export releases its source URL when the cloned image fails to load', async () => {
  const { downloadMarketChartPng } = await import('../src/lib/market-chart-download.ts');
  const previous = {
    Image: globalThis.Image,
    XMLSerializer: globalThis.XMLSerializer,
    getComputedStyle: globalThis.getComputedStyle,
    createObjectURL: URL.createObjectURL,
    revokeObjectURL: URL.revokeObjectURL,
  };
  const revoked = [];
  try {
    globalThis.getComputedStyle = () => ({ getPropertyValue: () => '#1b2128' });
    globalThis.XMLSerializer = class { serializeToString() { return '<svg/>'; } };
    globalThis.Image = class { set src(value) { queueMicrotask(() => this.onerror()); } };
    URL.createObjectURL = () => 'blob:source';
    URL.revokeObjectURL = (url) => revoked.push(url);
    await assert.rejects(downloadMarketChartPng(fakeSvg(), '2026-09-25'), /图表图片加载失败/);
    assert.deepEqual(revoked, ['blob:source']);
  } finally {
    globalThis.Image = previous.Image;
    globalThis.XMLSerializer = previous.XMLSerializer;
    globalThis.getComputedStyle = previous.getComputedStyle;
    URL.createObjectURL = previous.createObjectURL;
    URL.revokeObjectURL = previous.revokeObjectURL;
  }
});
