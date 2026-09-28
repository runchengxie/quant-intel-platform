const test = require('node:test');
const assert = require('node:assert/strict');

test('PNG export rasterizes the displayed SVG at 2x and releases object URLs', async () => {
  const { downloadMarketChartPng } = await import('../src/lib/market-chart-download.mjs');
  const previous = {
    Image: globalThis.Image,
    XMLSerializer: globalThis.XMLSerializer,
    document: globalThis.document,
    createObjectURL: URL.createObjectURL,
    revokeObjectURL: URL.revokeObjectURL,
    setTimeout: globalThis.setTimeout,
  };
  const revoked = [];
  const clicked = [];
  const canvas = {
    getContext: () => ({ scale: (...args) => clicked.push(['scale', ...args]), drawImage: (...args) => clicked.push(['draw', ...args]) }),
    toBlob: (callback, type) => callback(new Blob(['png'], { type })),
  };
  try {
    globalThis.XMLSerializer = class { serializeToString() { return '<svg width="960" height="600"/>'; } };
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
    await downloadMarketChartPng({ getAttribute: (key) => ({ width: '960', height: '600' })[key] }, '2026-09-25');
    assert.equal(canvas.width, 1920);
    assert.equal(canvas.height, 1200);
    assert.ok(clicked.some((row) => row[0] === 'draw'));
    assert.ok(clicked.some((row) => row[0] === 'scale' && row[1] === 2 && row[2] === 2));
    assert.ok(clicked.some((row) => row[0] === 'click' && row[1] === '2026-09-25-market-daily-charts.png'));
    assert.deepEqual(revoked, ['blob:test-image/png', 'blob:test-image/svg+xml;charset=utf-8']);
  } finally {
    globalThis.Image = previous.Image;
    globalThis.XMLSerializer = previous.XMLSerializer;
    globalThis.document = previous.document;
    URL.createObjectURL = previous.createObjectURL;
    URL.revokeObjectURL = previous.revokeObjectURL;
    globalThis.setTimeout = previous.setTimeout;
  }
});

test('PNG export removes the download link and releases URLs if the browser blocks the click', async () => {
  const { downloadMarketChartPng } = await import('../src/lib/market-chart-download.mjs');
  const previous = {
    Image: globalThis.Image,
    XMLSerializer: globalThis.XMLSerializer,
    document: globalThis.document,
    createObjectURL: URL.createObjectURL,
    revokeObjectURL: URL.revokeObjectURL,
    setTimeout: globalThis.setTimeout,
  };
  const revoked = [];
  let removed = false;
  try {
    globalThis.XMLSerializer = class { serializeToString() { return '<svg width="960" height="600"/>'; } };
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
    await assert.rejects(downloadMarketChartPng({ getAttribute: (key) => ({ width: '960', height: '600' })[key] }, '2026-09-25'), /download blocked/);
    assert.equal(removed, true);
    assert.deepEqual(revoked, ['blob:test-image/png', 'blob:test-image/svg+xml;charset=utf-8']);
  } finally {
    globalThis.Image = previous.Image;
    globalThis.XMLSerializer = previous.XMLSerializer;
    globalThis.document = previous.document;
    URL.createObjectURL = previous.createObjectURL;
    URL.revokeObjectURL = previous.revokeObjectURL;
    globalThis.setTimeout = previous.setTimeout;
  }
});
