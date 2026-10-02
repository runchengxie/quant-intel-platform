const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');

const evening = { id: '2026-09-30-evening', kind: 'evening', date: '2026-09-30', summary: '' };

test('published overview facts produce signed comparison and disjoint count groups', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  const markdown = `### 三、市场总览
全市场中位数涨跌 [WARN] -0.09% | 成交额加权涨跌 +0.98% | 总成交 1.45万亿
上涨 2567 家 | 下跌 2824 家 | 平盘 170 家 | 上涨率 46.2%
### 四、涨跌停
涨停 56 家 | 跌停 13 家 | 涨幅>5% 148 家 | 跌幅>5% 131 家
> 最高连板: 7 板
### 五、资金动向
大单资金代理 [WARN] -286.86亿 | 净流入 2065 家 / 净流出 3145 家`;
  const svg = buildAsiaReportSvg(evening, [], markdown);
  for (const key of ['overview', 'limits', 'flow']) assert.match(svg, new RegExp(`data-report-panel="${key}"`));
  assert.match(svg, /data-metric="median" data-value="-0.09"/);
  assert.match(svg, /data-metric="weighted" data-value="0.98"/);
  assert.match(svg, /data-count="limit-up" data-value="56"/);
  assert.match(svg, /data-count="over-five" data-value="148"/);
  assert.match(svg, /data-count="inflow" data-value="2065"/);
  assert.match(svg, /data-card="turnover"/);
  assert.match(svg, /data-card="max-board"/);
  assert.match(svg, /1.45万亿/);
  assert.match(svg, /-286.86/);
  assert.doesNotMatch(svg, /NaN|undefined/);
  const en = buildAsiaReportSvg(evening, [], markdown, value => value, 'en-US');
  assert.match(en, /Turnover-weighted return/);
  assert.match(en, /Large-order flow proxy/);
});

test('malformed overview remains visible without invented chart metrics', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  const svg = buildAsiaReportSvg(evening, [], '### 三、市场总览\n全市场中位数涨跌 N/A | 成交额加权涨跌 N/A');
  assert.match(svg, /N\/A/);
  assert.doesNotMatch(svg, /data-metric=/);
});

test('panels support the existing money formatter units and zero', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  for (const value of ['9000.00亿', '1.00万亿', '1000.00万', '0']) {
    const svg = buildAsiaReportSvg(evening, [], `### 三、市场总览\n全市场中位数涨跌 -0.09% | 成交额加权涨跌 +0.98% | 总成交 ${value}\n上涨 1 家 | 下跌 1 家 | 平盘 0 家 | 上涨率 50.0%`);
    assert.match(svg, /data-report-panel="overview"/);
  }
  for (const value of ['-0', '+1.00万', '+1.00万亿', '-286.86亿']) {
    const svg = buildAsiaReportSvg(evening, [], `### 五、资金动向\n大单资金代理 ${value} | 净流入 1 家 / 净流出 2 家`);
    assert.match(svg, /data-report-panel="flow"/);
  }
});

test('invalid turnover and inconsistent breadth remain text without graphics', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  for (const [amount, rate] of [['-1.45万亿', '50.0'], ['1.45万亿', '999.0'], ['1.45万亿', '20.0']]) {
    const svg = buildAsiaReportSvg(evening, [], `### 三、市场总览\n全市场中位数涨跌 -0.09% | 成交额加权涨跌 +0.98% | 总成交 ${amount}\n上涨 1 家 | 下跌 1 家 | 平盘 0 家 | 上涨率 ${rate}%\n第三行\n无法解析第四行`);
    assert.doesNotMatch(svg, /data-report-panel="overview"/);
    assert.match(svg, /无法解析第四行/);
  }
});

test('English financing disclosures expose partial and unknown coverage without Chinese', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  for (const scope of ['部分交易所，覆盖 SSE', '全市场，覆盖 BSE/SSE/SZSE', '部分交易所，覆盖 未核实']) {
    const charts = [{ key: 'dashboard', title: '综合盘面', status: 'degraded', reason: '融资余额仅覆盖部分交易所，保留一致范围和实际观测日', points: [
      { label: '融资余额 2026-09-29', value: 90, unit: '亿', observation_date: '2026-09-29', source_label: `Tushare 融资融券交易汇总（${scope}）`, source_url: 'https://tushare.pro' },
      { label: '融资余额 2026-09-30', value: 91, unit: '亿', observation_date: '2026-09-30', source_label: `Tushare 融资融券交易汇总（${scope}）`, source_url: 'https://tushare.pro' },
    ] }];
    const svg = buildAsiaReportSvg(evening, charts, '', value => value, 'en-US');
    assert.match(svg, /Covered exchanges/);
    assert.doesNotMatch(svg, /部分交易所|融资融券交易汇总|未核实|全市场|保留一致/);
  }
});
const facts = `### 二、指数总览
上证指数: 3842.19 [OK] +0.31% | 成交 6793.99亿
科创50: 1530.01 [WARN] -2.51% | 成交 718.79亿
深证成指: N/A [WARN] N/A | 成交 N/A
### 七、行业板块 TOP10
| 行业 | 均涨跌 | 中位数 | 家数 | 上涨率 |
|---|---|---|---|---|
| 医药生物 | +2.00% | +1.57% | 464 | 83.4% |
| A \\| B <script> | N/A | -1.00% | 12 | N/A |
| broken | +5% |
### 八、高成交核心票 TOP10
| 代码 | 成交额(亿) | 涨跌 |
|---|---|---|
| 300308 | 128.5 | -0.56% |
### 九、热门概念 TOP5
| 概念 | 涨幅 | 龙头 | 涨停数 |
|---|---|---|---|
| mRNA概念 | +6.42% | 康希诺(+20.00%) | 1 |
### 十、极端异动
涨幅前五: 301190.SZ(+20.01%)、688185.SH(+20.00%)
跌幅前五: 920202.BJ(-29.97%)
*数据: Tushare / market-data-platform | 生成: 2026-09-30 18:45*`;

test('published facts produce aligned tables, signed index geometry and explicit malformed fallback', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  const svg = buildAsiaReportSvg(evening, [], facts);
  for (const key of ['indices', 'industry', 'turnover', 'concepts', 'movers']) {
    assert.match(svg, new RegExp(`data-table="${key}"`));
  }
  assert.match(svg, />收盘点位<\/text>/);
  assert.match(svg, />成交额（亿）<\/text>/);
  assert.match(svg, />3842\.19<\/text>/);
  assert.match(svg, />6793\.99<\/text>/);
  const bars = [...svg.matchAll(/<rect data-index-return="([^"]+)" data-value="([^"]+)" x="([^"]+)" y="([^"]+)" width="([^"]+)"/g)];
  assert.equal(bars.length, 2);
  const positive = bars.find((row) => row[2] === '0.31');
  const negative = bars.find((row) => row[2] === '-2.51');
  assert.equal(Number(positive[3]), 540);
  assert.equal(Number(negative[3]) + Number(negative[5]), 540);
  assert.ok(Number(positive[5]) < Number(negative[5]));
  assert.match(svg, /无法解析|缺项/);
  assert.match(svg, /broken/);
  assert.match(svg, /N\/A/);
  assert.match(svg, /A \| B &lt;script&gt;/);
  assert.match(svg, /2026-09-30 18:45/);
  assert.match(svg, />-29\.97%<\/text>/);
  assert.doesNotMatch(svg, /\[OK\]|\[WARN\]|<script>|NaN|undefined/);
  const industry = svg.match(/<g data-table="industry">([\s\S]*?)<\/g>/)[1];
  const positions = [...industry.matchAll(/<text x="([^"]+)" y="([^"]+)"[^>]*>(行业|均涨跌|中位数|家数|上涨率)<\/text>/g)];
  assert.equal(positions.length, 5);
  assert.equal(new Set(positions.map((row) => row[2])).size, 1);
  assert.equal(new Set(positions.map((row) => row[1])).size, 5);
});

test('English table labels are complete and geometry is shared with Chinese', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  const { toEnglishPresentation } = await import('../src/lib/english-content.ts');
  const en = buildAsiaReportSvg(evening, [], facts, toEnglishPresentation);
  assert.match(en, />Close level<\/text>/);
  assert.match(en, />Turnover \(CNY 100m\)<\/text>/);
  assert.match(en, />Index daily returns<\/text>/);
  assert.match(en, /Unparsed row/);
  assert.match(en, /Original report facts/);
  assert.doesNotMatch(en, /收盘点位|成交额（亿）|指数日涨跌|\[WARN\]/);
  assert.match(en, /data-value="-2.51" x="240"/);
});

test('new English labels come from the selected semantic catalog without substring translation', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  // Legacy presenter identifies English but deliberately does not know new labels.
  const legacy = (value) => value === '亚洲市场收盘复盘' ? 'Asia market close review' : value;
  const svg = buildAsiaReportSvg(evening, [], facts, legacy);
  assert.match(svg, />Close level<\/text>/);
  assert.match(svg, />Turnover \(CNY 100m\)<\/text>/);
  assert.match(svg, />Index daily returns<\/text>/);
  assert.match(svg, /Original report facts/);
});

test('explicit English locale selects labels and metadata with identity or custom presenters', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  for (const present of [(value) => value, (value) => value.replace('301190.SZ', 'custom ticker')]) {
    const svg = buildAsiaReportSvg(evening, [], facts, present, 'en-US');
    assert.match(svg, /<title>2026-09-30 Asia market close review<\/title>/);
    assert.match(svg, /<desc>Includes the Asia close summary/);
    assert.match(svg, /19:00 Beijing time edition/);
    assert.match(svg, />Close level<\/text>/);
    assert.match(svg, />Index daily returns<\/text>/);
    assert.doesNotMatch(svg, /亚洲市场收盘|北京时间|收盘点位|指数日涨跌/);
  }
});

test('English prose wraps at word boundaries instead of splitting translated words', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  const svg = buildAsiaReportSvg({ ...evening, summary: 'alpha '.repeat(15) + 'fragmentation matters' }, [], '', (value) => value, 'en-US');
  const text = [...svg.matchAll(/<text\b[^>]*>([^<]*)<\/text>/g)].map((row) => row[1]);
  assert.ok(text.some((line) => line.includes('fragmentation')));
});

test('table previews retain fallback and point readers to full details', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  const rows = Array.from({ length: 10 }, (_, i) => `| ${300000 + i} | ${100 - i}.0 | +1.00% |`).join('\n');
  const svg = buildAsiaReportSvg(evening, [], `### 八、高成交核心票 TOP10\n| 代码 | 成交额(亿) | 涨跌 |\n|---|---|---|\n${rows}`);
  assert.match(svg, /300004/);
  assert.doesNotMatch(svg, /300005/);
  assert.match(svg, /5.*10/);
  assert.match(svg, /完整报告/);
});

test('English previews translate complete templates and retain original date/source attribution', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  const { toEnglishPresentation } = await import('../src/lib/english-content.ts');
  const rows = Array.from({ length: 10 }, (_, i) => `| ${300000 + i} | 99.0 | +1.00% |`).join('\n');
  const svg = buildAsiaReportSvg(evening, [], `### 八、高成交核心票 TOP10\n| 代码 | 成交额(亿) | 涨跌 |\n|---|---|---|\n${rows}\n*数据: A < B & \"C\" | 生成: 2026-09-30 18:45*`, toEnglishPresentation);
  assert.match(svg, /Preview 5 \/ 10 rows; see the full report for the rest\./);
  assert.match(svg, /Data: A &lt; B &amp; &quot;C&quot;/);
  assert.match(svg, /Generated: 2026-09-30 18:45/);
  assert.doesNotMatch(svg, /预览|完整报告|暂无|缺少|跳过/);
});

test('malformed index returns and table schemas remain explicit without partial or invented bars', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  const svg = buildAsiaReportSvg(evening, [], `### 二、指数总览
上证指数: 3842.19 [OK] +0.31oops% | 成交 6793.99亿
科创50: N/A [WARN] N/A | 成交 N/A
沪深300: 4357.62 [OK] +0.00% | 成交 3564.92亿
### 九、热门概念 TOP5
| wrong | 涨幅 | 龙头 | 涨停数 |
|---|---|---|---|
| bad | +1.00% | x | 1 |`);
  assert.match(svg, /0.31oops%/);
  assert.match(svg, /日涨跌缺项/);
  assert.match(svg, /wrong/);
  assert.match(svg, /bad/);
  const bars = [...svg.matchAll(/data-index-return="([^"]+)" data-value="([^"]+)"[^>]*width="([^"]+)"/g)];
  assert.equal(bars.length, 1);
  assert.deepEqual(bars[0].slice(1), ['沪深300', '0', '0']);
  assert.doesNotMatch(svg, /\[OK\]|\[WARN\]|NaN/);
});

test('unterminated table rows are explicit fallback even after preview notes', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  const svg = buildAsiaReportSvg(evening, [], `### 八、高成交核心票 TOP10\n| 代码 | 成交额(亿) | 涨跌 |\n|---|---|---|\nnote one\nnote two\n| 600001 | 10.0 | +2.00%`);
  assert.match(svg, /无法解析的原始行: \| 600001/);
});

for (const scenario of [
  { heading: '### 七、行业板块 TOP10', key: 'industry', header: '| 行业 | 均涨跌 | 中位数 | 家数 | 上涨率 |', columns: 5,
    invalid: [
      '| InvalidMean | nope | +1.00% | 12 | 50.0% |',
      '| InvalidMedian | +1.00% | NaN | 12 | 50.0% |',
      '| InvalidCount | +1.00% | -1.00% | -3 | 50.0% |',
      '| DecimalCount | +1.00% | -1.00% | 3.5 | 50.0% |',
      '| InvalidRate | +1.00% | -1.00% | 12 | 101.0% |',
      '| NegativeRate | +1.00% | -1.00% | 12 | -1.0% |',
      '| EmptyRate | +1.00% | -1.00% | 12 | |',
      '| | +1.00% | -1.00% | 12 | 50.0% |',
    ] },
  { heading: '### 八、高成交核心票 TOP10', key: 'turnover', header: '| 代码 | 成交额(亿) | 涨跌 |', columns: 3,
    invalid: [
      '| 12345 | 10.0 | +1.00% |', '| ABCDEF | 10.0 | +1.00% |',
      '| 600001 | -10.0 | +1.00% |', '| 600001 | Infinity | +1.00% |',
      '| 600001 | 0x10 | +1.00% |', '| 600001 | 1e3 | +1.00% |',
      '| 600001 | 10.0 | NaN |', '| 600001 | 10.0 | +1oops% |',
      '| 600001 | | +1.00% |',
    ] },
  { heading: '### 九、热门概念 TOP5', key: 'concepts', header: '| 概念 | 涨幅 | 龙头 | 涨停数 |', columns: 4,
    invalid: [
      '| | +1.00% | 原名(+2.00%) | 2 |', '| InvalidReturn | nope | 原名(+2.00%) | 2 |',
      '| EmptyLeader | +1.00% | | 2 |', '| InvalidLeader | +1.00% | 原名(+oops%) | 2 |',
      '| InvalidCount | +1.00% | 原名(+2.00%) | -2 |', '| DecimalCount | +1.00% | 原名(+2.00%) | 2.5 |',
    ] },
]) {
  test(`${scenario.key} rejects same-column invalid fields from the rendered numeric table`, async () => {
    const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
    for (const invalid of scenario.invalid) {
      const svg = buildAsiaReportSvg(evening, [], `${scenario.heading}\n${scenario.header}\n|---|---|---|\n${invalid}`);
      const table = svg.match(new RegExp(`<g data-table="${scenario.key}">([\\s\\S]*?)<\\/g>`))[1];
      assert.equal((table.match(/<text\b/g) || []).length, scenario.columns, invalid);
      assert.match(svg, /无法解析的原始行/, invalid);
      assert.ok(svg.includes(invalid), invalid);
    }
  });
}

test('validated tables preserve explicit N/A, published unsigned zero and large finite values', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  const svg = buildAsiaReportSvg(evening, [], `### 七、行业板块 TOP10
| 行业 | 均涨跌 | 中位数 | 家数 | 上涨率 |
|---|---|---|---|---|
| MissingIndustry | N/A | 0.00% | N/A | N/A |
| LargeIndustry | +1000.00% | -1000.00% | 1000000 | 100.0% |
### 八、高成交核心票 TOP10
| 代码 | 成交额(亿) | 涨跌 |
|---|---|---|
| 001246 | 1000000000000000.0 | +206.59% |
| 000001 | N/A | N/A |
### 九、热门概念 TOP5
| 概念 | 涨幅 | 龙头 | 涨停数 |
|---|---|---|---|
| MissingConcept | N/A | N/A | N/A |
| LargeConcept | +1000.00% | 源名(+1000.00%) | 1000000 |`);
  assert.doesNotMatch(svg, /无法解析的原始行/);
  assert.match(svg, /源名\(\+1000\.00%\)/);
  assert.match(svg, />001246<\/text>/);
  assert.match(svg, />1000000000000000\.0<\/text>/);
  assert.match(svg, />N\/A<\/text>/);
  assert.match(svg, />0\.00%<\/text>/);
});

test('syntactically decimal values that overflow finite numbers remain visible fallback', async () => {
  const { buildAsiaReportSvg } = await import('../src/lib/asia-report-image.ts');
  const huge = '9'.repeat(310);
  for (const row of [`| 600001 | ${huge} | +1.00% |`, `| 600001 | 10.0 | +${huge}% |`]) {
    const svg = buildAsiaReportSvg(evening, [], `### 八、高成交核心票 TOP10\n| 代码 | 成交额(亿) | 涨跌 |\n|---|---|---|\n${row}`);
    const table = svg.match(/<g data-table="turnover">([\s\S]*?)<\/g>/)[1];
    assert.equal((table.match(/<text\b/g) || []).length, 3);
    assert.match(svg, /无法解析的原始行: \| 600001/);
    assert.doesNotMatch(svg, /Infinity|NaN/);
  }
});

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
  assert.match(svg, /fill="var\(--report-bg/);
  assert.match(svg, /fill="var\(--report-ink/);
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
