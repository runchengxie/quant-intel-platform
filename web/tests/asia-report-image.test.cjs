const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');

test('Asia report image combines the evening framework, five local chart states and sources', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  const report = { id: '2026-09-25-evening', kind: 'evening', date: '2026-09-25', summary: '亚洲市场收盘。' };
  const charts = [
    { key: 'dashboard', title: '综合仪表盘', status: 'ok', points: [
      { label: '上涨家数', value: 1200, unit: '家', observation_date: '2026-09-25',
        source_label: '公开行情', source_url: 'https://example.com/market' },
    ] },
    ...[['moneyflow', '资金流向图'], ['topic', '热点概念图'], ['sentiment', '情绪指标图'],
      ['us_overnight', '美股隔夜图'], ['weekly_chart', '周度概览图']].map(([key, title]) =>
      ({ key, title, status: 'missing', reason: '待核实', points: null })),
  ];
  const markdown = '## 一、市场状态\n- 状态: 偏冷。\n### 核心矛盾\n- 市场分歧。\n### 明日验证\n- 观察广度。\n### 三、市场总览\n上涨 1200 家。';
  const svg = buildAsiaReportSvg(report, charts, markdown);
  assert.match(svg, /亚洲市场收盘复盘/);
  assert.match(svg, /市场分歧/);
  assert.match(svg, /观察广度/);
  for (const title of ['综合盘面', '资金流向', '热点概念', '市场温度', '周度概览']) assert.match(svg, new RegExp(title));
  assert.doesNotMatch(svg, /美股隔夜图|六图概览/);
  assert.match(svg, /观测日：2026-09-25/);
  assert.match(svg, /example.com/);
  assert.doesNotMatch(svg, /NaN|undefined/);
});

test('real evening data uses breadth, trend and money flow visuals without overnight US quotes', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  const publicRoot = path.join(__dirname, '../artifacts/public');
  const reportId = '2026-09-24-evening';
  const report = JSON.parse(readFileSync(path.join(publicRoot, 'data/reports.json'), 'utf8'))
    .reports.find((row) => row.id === reportId);
  const charts = JSON.parse(readFileSync(path.join(publicRoot, `data/charts/${reportId}.json`), 'utf8')).charts;
  const markdown = readFileSync(path.join(publicRoot, `reports/${reportId}.md`), 'utf8');
  const svg = buildAsiaReportSvg(report, charts, markdown);
  assert.match(svg, /市场广度/);
  assert.match(svg, /融资余额走势/);
  assert.match(svg, /成交额走势/);
  assert.match(svg, /主力净流入/);
  assert.match(svg, /近几日涨跌分布/);
  assert.match(svg, /<polyline/);
  assert.doesNotMatch(svg, /美股隔夜图|标普500 ETF|Meta/);
  assert.match(svg, /观测日：2026-09-18 至 2026-09-24/);
  assert.match(svg, /data-dimension="流动性"/);
  assert.match(svg, /data-dimension="亏钱风险"/);
  assert.match(svg, /亏钱风险越高，风险越高/);
  assert.match(svg, /成交额分位 15\.0%/);
});

test('six-dimensional chart rejects invalid scores and escapes evidence', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  const report = { id: '2026-09-25-evening', kind: 'evening', date: '2026-09-25', summary: '' };
  const markdown = '### 六维观察\n| 维度 | 观察分 | 状态 | 证据 |\n|---|---:|---|---|\n'
    + '| 流动性 | 75 | 较强 | 成交额改善 <script> |\n'
    + '| 亏钱风险 | N/A | 缺项 | 数据不足 |\n';
  const svg = buildAsiaReportSvg(report, [], markdown);
  assert.match(svg, /data-dimension="流动性"/);
  assert.match(svg, /成交额改善 &lt;script&gt;/);
  assert.match(svg, /亏钱风险 · 缺项/);
  assert.match(svg, /数据不足/);
  assert.doesNotMatch(svg, /data-dimension="亏钱风险"|NaN/);
});

test('six-dimensional chart accepts escaped evidence pipes but rejects non-decimal scores', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  const report = { id: '2026-09-25-evening', kind: 'evening', date: '2026-09-25', summary: '' };
  const markdown = '### 六维观察\n| 维度 | 观察分 | 状态 | 证据 |\n|---|---:|---|---|\n'
    + '| 流动性 | 30.5 | 偏弱 | 数据 A \\| 数据 B |\n'
    + '| 广度 | 0x10 | 缺项 | 数据格式错误 |\n';
  const svg = buildAsiaReportSvg(report, [], markdown);
  assert.match(svg, /data-dimension="流动性"/);
  assert.match(svg, /数据 A \| 数据 B/);
  assert.match(svg, /广度 · 缺项/);
  assert.match(svg, /数据格式错误/);
  assert.doesNotMatch(svg, /data-dimension="广度"/);
});

test('Asia report image escapes public text and rejects a morning identity', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  const report = { id: '2026-09-25-evening', kind: 'evening', date: '2026-09-25', summary: '<script>alert(1)</script>' };
  assert.match(buildAsiaReportSvg(report, [], ''), /&lt;script&gt;/);
  assert.equal(buildAsiaReportSvg({ ...report, kind: 'morning' }, [], ''), null);
});
