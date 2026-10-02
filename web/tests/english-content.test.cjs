const test = require('node:test');
const assert = require('node:assert/strict');
const { toEnglishPresentation: present } = require('../src/lib/english-content.ts');
const { toOption } = require('../src/lib/chart-data.ts');
const { buildAsiaReportSvg } = require('../src/lib/asia-report-image.ts');

test('reviewed session charts translate titles and limitations without duplicate punctuation', () => {
  assert.equal(present('近5个交易日数据概览'), 'Last five trading sessions');
  assert.equal(present('使用替代来源或非目标日观测值'),
    'An alternative source or an observation outside the target date is used');
  assert.equal(present('融资余额仅覆盖部分交易所，保留一致范围和实际观测日。'),
    'Financing balances cover only some exchanges. Comparable coverage and actual observation dates are retained.');
});

test('currency presentation never assigns CNY to dollar or unspecified amounts', () => {
  assert.equal(present('186.8亿美元'), '186.8 USD 100m');
  assert.equal(present('177.5亿至184亿美元'), '177.5 100m to 184 USD 100m');
  assert.equal(present('12.41亿元'), '12.41 CNY 100m');
  assert.equal(present('1.45万亿'), '1.45 trillion');
});

test('English presentation does not split company names into translated characters', () => {
  assert.equal(present('我爱我家 000560'), '我爱我家 000560');
  assert.equal(present('工商银行 601398'), '工商银行 601398');
  assert.equal(present('A股指数'), 'A股指数');
  assert.equal(present('mRNA概念公司'), 'mRNA概念公司');
  assert.equal(present('A行业'), 'A行业');
  assert.equal(present('mRNA概念A'), 'mRNA概念A');
});

test('compound metrics and state grades translate as complete terms', () => {
  assert.equal(present('上涨率 46.2%；个股中位涨跌 -0.1%'), 'Advancing share 46.2%; Median stock return -0.1%');
  assert.equal(present('中性偏冷'), 'Neutral to cool');
  assert.equal(present('偏弱'), 'Somewhat weak');
  assert.equal(present('已核实'), 'Verified');
  assert.equal(present('部分缺项'), 'Degraded');
});

test('dynamic explanatory prose keeps numeric conditions while translating entire clauses', () => {
  assert.equal(present('行业层面多数上涨，但个股广度没有同步确认；证据: 上涨行业占比: 59.4%；上涨率: 46.2%'),
    'Most sectors advanced, but stock breadth did not confirm the move; Evidence: Advancing sector share: 59.4%; Advancing share: 46.2%');
  assert.equal(present('融资余额最新观测日早于上一交易日，保留原始观测日'),
    'The latest financing-balance observation predates the previous session; original observation dates are preserved');
});

test('SVG translation changes text but not URLs or attributes', () => {
  assert.equal(present('<svg id="市场状态"><text>市场状态</text><a href="https://example.com/行业">行业</a></svg>'),
    '<svg id="市场状态"><text>Market state</text><a href="https://example.com/行业">Industry</a></svg>');
  assert.equal(present('Source: https://example.com/行业'), 'Source: https://example.com/行业');
  assert.equal(present('<svg><text data-note="a > 行业">行业</text></svg>'),
    '<svg><text data-note="a > 行业">Industry</text></svg>');
  assert.equal(present('[行业](/data/行业)'), '[Industry](/data/行业)');
});

test('English interactive charts retain numeric risk axes and translate tooltip labels', () => {
  const card = { title: '市场温度', key: 'sentiment', points: [
    { label: '亏钱风险', value: 19.5, unit: '观察分（风险）', observation_date: '2026-09-30', source_label: 'Tushare A股晚报六维观察', source_url: 'https://tushare.pro/document/2?doc_id=181' },
  ] };
  const option = toOption(card, undefined, 'en');
  assert.equal(option.yAxis.min, 0);
  assert.equal(option.yAxis.max, 100);
  assert.equal(option.series[0].data[0].value, 19.5);
  assert.deepEqual(option.xAxis.data, ['Loss risk']);
  const tooltip = option.tooltip.formatter({ dataIndex: 0 });
  assert.doesNotMatch(tooltip, /[\u4e00-\u9fff]/);
  assert.match(tooltip, /19.5/);
});

test('English explanatory clauses translate before SVG line wrapping', () => {
  const svg = buildAsiaReportSvg({ kind: 'evening', id: '2026-09-30-evening', date: '2026-09-30', summary: '' }, [],
    '## 一、市场状态\n口径: 热度、脆弱度与六维分数均为市场状态观察分，不直接映射仓位，也不构成交易指令。', present);
  assert.match(svg, /Heat, fragility/);
  assert.doesNotMatch(svg, /热度|映射仓位|交易指令/);
});
