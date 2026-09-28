const test = require('node:test');
const assert = require('node:assert/strict');

test('Asia report image combines the evening framework, all six chart states and sources', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.mjs');
  const report = { id: '2026-09-25-evening', kind: 'evening', date: '2026-09-25', summary: '亚洲市场收盘。' };
  const charts = [
    { title: '综合仪表盘', status: 'ok', points: [
      { label: '上涨家数', value: 1200, unit: '家', observation_date: '2026-09-25',
        source_label: '公开行情', source_url: 'https://example.com/market' },
    ] },
    ...['资金流向图', '热点概念图', '情绪指标图', '美股隔夜图', '周度概览图'].map((title) =>
      ({ title, status: 'missing', reason: '待核实', points: null })),
  ];
  const markdown = '## 一、市场状态\n- 状态: 偏冷。\n### 核心矛盾\n- 市场分歧。\n### 明日验证\n- 观察广度。\n### 三、市场总览\n上涨 1200 家。';
  const svg = buildAsiaReportSvg(report, charts, markdown);
  assert.match(svg, /亚洲市场收盘复盘/);
  assert.match(svg, /市场分歧/);
  assert.match(svg, /观察广度/);
  for (const chart of charts) assert.match(svg, new RegExp(chart.title));
  assert.match(svg, /观测日 2026-09-25/);
  assert.match(svg, /example.com/);
  assert.doesNotMatch(svg, /NaN|undefined/);
});

test('Asia report image escapes public text and rejects a morning identity', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.mjs');
  const report = { id: '2026-09-25-evening', kind: 'evening', date: '2026-09-25', summary: '<script>alert(1)</script>' };
  assert.match(buildAsiaReportSvg(report, [], ''), /&lt;script&gt;/);
  assert.equal(buildAsiaReportSvg({ ...report, kind: 'morning' }, [], ''), null);
});
