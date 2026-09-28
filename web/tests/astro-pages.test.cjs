const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync, existsSync, cpSync, writeFileSync, mkdtempSync, rmSync, readdirSync } = require('node:fs');
const { execFileSync } = require('node:child_process');
const path = require('node:path');

const root = path.join(__dirname, '..');

test('legacy page reads public data and reports from the site root', () => {
  const app = readFileSync(path.join(root, 'src/legacy/app.js'), 'utf8');
  assert.match(app, /fetch\("\.\.\/data\/reports\.json"/);
  assert.match(app, /fetch\("\.\.\/data\/market_daily_report\.json"/);
  assert.match(app, /fetch\("\.\.\/data\/daily_summaries\.json"/);
  assert.match(app, /optionalIndex\("\.\.\/data\/insights\.json"/);
  assert.match(app, /optionalIndex\("\.\.\/data\/health\.json"/);
  assert.match(app, /link\.href = `\.\.\/reports\//);
  assert.match(app, /source\.href = `\.\.\/\$\{report\.source_url\}`/);
});

test('Astro emits a readable five-session static site with six chart states', () => {
  execFileSync('npm', ['run', 'build'], { cwd: root, stdio: 'pipe' });
  const index = readFileSync(path.join(root, 'dist/index.html'), 'utf8');
  const reports = JSON.parse(readFileSync(path.join(root, 'artifacts/public/data/reports.json'), 'utf8')).reports;
  const reportId = reports[0].id;
  assert.match(index, /Quant 市场情报/);
  assert.ok(index.includes('/quant-intel-platform/'));
  assert.ok(!index.includes('/market-intel-pages/'));
  assert.match(index, /id="theme-toggle"/);
  assert.match(index, /id="us-session"/);
  assert.match(index, /id="asia-session"/);
  assert.match(index, /07:00 美股收盘复盘/);
  assert.match(index, /19:00 亚洲市场收盘复盘/);
  assert.match(index, /旧晨报保留归档/);
  assert.match(index, /市场驱动/);
  assert.match(index, /展开完整已核实报告/);
  assert.ok(index.indexOf('<h3>美股收盘</h3>') < index.indexOf('<h3>重点个股</h3>'));
  assert.ok(index.indexOf('<h3>重点个股</h3>') < index.indexOf('<h3>美债收益率</h3>'));
  assert.ok(index.indexOf('<h3>美债收益率</h3>') < index.indexOf('<h3>跨资产行情</h3>'));
  assert.match(index, /<th>5 年<\/th><td>4\.980%/);
  assert.match(index, /<th>30 年<\/th><td>5\.490%/);
  assert.match(index, /Markdown 原文/);
  assert.match(index, /id="market-daily-chart"/);
  assert.match(index, /<details class="market-chart"/);
  assert.match(index, /id="download-market-chart"/);
  const chart = index.match(/<div class="market-chart-graphic" id="market-daily-chart">([\s\S]*?)<\/div>/)?.[1];
  assert.ok(chart);
  assert.match(chart, /2026-09-25 美东交易日市场图表/);
  assert.match(chart, /观测日 2026-09-25/);
  assert.doesNotMatch(chart, /home\.treasury\.gov|来源/);
  assert.match(chart, /BTC\/USD 现货/);
  assert.match(chart, /2026-08-01|2026-07-01/);
  assert.doesNotMatch(index, /美国财政部<\/a><a[^>]*>美国财政部/);
  assert.doesNotMatch(index, /Yahoo Finance<\/a><a[^>]*>Yahoo Finance/);
  assert.doesNotMatch(index, /FMP<\/a><a[^>]*>FMP/);
  const styles = readdirSync(path.join(root, 'dist/_astro')).filter((name) => name.endsWith('.css'))
    .map((name) => readFileSync(path.join(root, `dist/_astro/${name}`), 'utf8')).join('\n');
  assert.match(styles, /:root\[data-theme=?"?dark/);
  assert.ok(index.includes(reportId));
  const report = path.join(root, `dist/reports/${reportId}/index.html`);
  assert.ok(existsSync(report));
  const html = readFileSync(report, 'utf8');
  assert.match(html, /class="panel report-body markdown-body"/);
  assert.match(html, /data-chart-key="dashboard"/);
  assert.match(html, /data-chart-key="weekly_chart"/);
  assert.ok(html.includes(`/quant-intel-platform/reports/${reportId}.md`));
  assert.doesNotMatch(html, /private-chat-target/);
  assert.doesNotMatch(index, /echarts\.|ChartIsland\.|\.png["']/);
  assert.doesNotMatch(html, /echarts\.|ChartIsland\.|\.png["']/);
  assert.match(index, /<a href="https:\/\/home\.treasury\.gov[^"]*"[^>]*>美国财政部<\/a>/);
  assert.doesNotMatch(index, /\| 流动性 \|/);
  assert.match(html, /<table>/);
});

test('US daily chart is absent when the public report has no eligible market facts', () => {
  const fixture = mkdtempSync(path.join(path.dirname(root), 'market-daily-empty-chart-'));
  try {
    cpSync(path.join(root, 'artifacts/public/data'), path.join(fixture, 'data'), { recursive: true });
    cpSync(path.join(root, 'artifacts/public/reports'), path.join(fixture, 'reports'), { recursive: true });
    const file = path.join(fixture, 'data/market_daily_report.json');
    const report = JSON.parse(readFileSync(file, 'utf8'));
    report.facts = report.facts.filter((fact) => fact.id.startsWith('macro.'));
    writeFileSync(file, JSON.stringify(report));
    execFileSync('npm', ['run', 'build', '--', '--outDir', path.join(fixture, 'built')], {
      cwd: root, stdio: 'pipe', env: { ...process.env, ASTRO_DATA_ROOT: fixture },
    });
    const html = readFileSync(path.join(fixture, 'built/index.html'), 'utf8');
    assert.doesNotMatch(html, /id="market-daily-chart"/);
    assert.doesNotMatch(html, /id="download-market-chart"/);
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});

test('Astro market brief shows verified primary facts, semantic sources and compact secondary content', () => {
  const fixture = mkdtempSync(path.join(path.dirname(root), 'market-daily-brief-'));
  try {
    cpSync(path.join(root, 'artifacts/public/data'), path.join(fixture, 'data'), { recursive: true });
    cpSync(path.join(root, 'artifacts/public/reports'), path.join(fixture, 'reports'), { recursive: true });
    const file = path.join(fixture, 'data/market_daily_report.json');
    const report = JSON.parse(readFileSync(file, 'utf8'));
    const reportDate = report.run_id.slice(6);
    const fact = (id, value, unit, source, source_url, metric, observation_date) => ({
      id, value, unit, source, source_url, metric, observation_date,
    });
    report.facts.push(
      fact('treasury.2y.level_percent', 3.85, 'percent', 'US Treasury', 'https://home.treasury.gov/data', 'yield_level', reportDate),
      fact('cross_asset.brent.close', 68.25, 'USD/barrel', 'Yahoo Finance', 'https://finance.yahoo.com/quote/BZ=F/', 'close', reportDate),
      fact('cross_asset.brent.change_percent', 1.25, 'percent', 'Yahoo Finance', 'https://finance.yahoo.com/quote/BZ=F/', 'daily_return', reportDate),
      fact('cross_asset.silver.close', 64.8, 'USD/troy_ounce', 'Financial Modeling Prep', 'https://site.financialmodelingprep.com/developer/docs/stable/commodities-historical-price-eod-full', 'commodity_close', reportDate),
      fact('cross_asset.silver.change_percent', 1.24, 'percent', 'Financial Modeling Prep', 'https://site.financialmodelingprep.com/developer/docs/stable/commodities-historical-price-eod-full', 'daily_return', reportDate),
      fact('cross_asset.bitcoin_spot.close', 84093.13, 'USD/bitcoin', 'Financial Modeling Prep', 'https://site.financialmodelingprep.com/developer/docs/stable/cryptocurrency-historical-price-eod-full', 'crypto_spot_close', reportDate),
      fact('cross_asset.bitcoin_spot.change_percent', -0.35, 'percent', 'Financial Modeling Prep', 'https://site.financialmodelingprep.com/developer/docs/stable/cryptocurrency-historical-price-eod-full', 'daily_return', reportDate),
    );
    for (const rate of report.facts.filter((row) => row.id.startsWith('treasury.2y.'))) {
      rate.source = 'FRED';
      rate.source_url = 'https://fred.stlouisfed.org/series/DGS2';
    }
    writeFileSync(file, JSON.stringify(report));
    execFileSync('npm', ['run', 'build', '--', '--outDir', path.join(fixture, 'built')], {
      cwd: root, stdio: 'pipe', env: { ...process.env, ASTRO_DATA_ROOT: fixture },
    });
    const html = readFileSync(path.join(fixture, 'built/index.html'), 'utf8');
    assert.match(html, /美股收盘/);
    assert.match(html, /美债收益率/);
    assert.match(html, /3\.850%/);
    assert.match(html, /跨资产行情/);
    assert.match(html, /68\.25 USD\/barrel/);
    assert.match(html, /BTC\/USD 现货/);
    assert.match(html, /84,093\.13 USD\/bitcoin/);
    assert.match(html, />美国财政部</);
    assert.match(html, /<a href="https:\/\/fred\.stlouisfed\.org\/series\/DGS2"[^>]*>FRED<\/a>/);
    assert.match(html, />Yahoo Finance</);
    assert.match(html, />FMP</);
    assert.match(html, /Yahoo Finance/);
    assert.match(html, /展开完整已核实报告/);
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});

test('all visible US daily Markdown editions disclose public source quality', () => {
  const history = JSON.parse(readFileSync(path.join(root, 'artifacts/public/data/market_daily_reports.json'), 'utf8'));
  for (const report of history.reports) {
    const date = report.run_id.slice(6);
    const markdown = readFileSync(path.join(root, `artifacts/public/reports/${date}-market-daily.md`), 'utf8');
    assert.match(markdown, /## 数据质量与核验说明/);
    if (report.source_status.research?.reason === 'not_connected') {
      assert.match(markdown, /研究材料尚未接入，不提供未经核实的解释/);
    }
  }
});

test('historical insight discloses timing, limitations and verification units', () => {
  const insight = JSON.parse(readFileSync(path.join(root, 'artifacts/public/data/insights.json'), 'utf8')).insights[0];
  if (!insight) return;
  const index = readFileSync(path.join(root, 'dist/index.html'), 'utf8');
  assert.match(index, /信息截至/);
  assert.match(index, /解读生成/);
  if (insight.generation_mode === 'retrospective') assert.match(index, /历史材料回放/);
  if (insight.quality_warnings.length) assert.match(index, /数据缺项与限制/);
  const point = insight.analysis.watchpoints[0];
  if (point) {
    assert.ok(index.includes(insight.metrics[point.metric].label));
    assert.match(index, /待验证|条件满足|条件未满足|数据不足，无法验证/);
  }
});

test('GFM tables render but untrusted HTML and script URLs are removed', async () => {
  const { renderMarkdown } = await import('../src/lib/markdown.mjs');
  const html = renderMarkdown('| 维度 | 值 |\n|---|---:|\n| 流动性 | 17.1 |\n\n<script>alert(1)</script>\n[bad](javascript:alert(1))');
  assert.match(html, /<table>/);
  assert.match(html, /流动性/);
  assert.doesNotMatch(html, /<script|href="javascript:/);
});

test('market daily source URLs become compact numbered links only in the rendered page', async () => {
  const { renderMarkdown } = await import('../src/lib/markdown.mjs');
  const source = '- 来源：https://example.com/one, https://example.org/two';
  const html = renderMarkdown(source, { compactSources: true });
  assert.match(html, /<a href="https:\/\/example.com\/one"[^>]*>来源1<\/a>/);
  assert.match(html, /<a href="https:\/\/example.org\/two"[^>]*>来源2<\/a>/);
  assert.doesNotMatch(html, />https:\/\/example.com\/one</);
  assert.match(renderMarkdown(source), /https:\/\/example.com\/one/);
});

test('single table-row evidence is labelled instead of showing raw Markdown pipes', async () => {
  const { formatEvidenceLine } = await import('../src/lib/evidence.mjs');
  assert.equal(formatEvidenceLine('六维观察', '| 流动性 | 25.4 | 偏弱 | 成交额/历史中位 0.90x |'),
    '维度：流动性；观察分：25.4；状态：偏弱；证据：成交额/历史中位 0.90x');
  assert.equal(formatEvidenceLine('七、行业板块 TOP10', '| 电子 | +0.94% | +0.53% | 436 | 59.9% |'),
    '行业：电子；均涨跌：+0.94%；中位数：+0.53%；家数：436；上涨率：59.9%');
  assert.equal(formatEvidenceLine('市场总览', '上涨 1891 家 | 下跌 3564 家'), '上涨 1891 家 | 下跌 3564 家');
});

test('verified watchpoint outcome shows labelled table evidence', () => {
  const fixture = mkdtempSync(path.join(path.dirname(root), 'market-insight-outcome-'));
  try {
    cpSync(path.join(root, 'artifacts/public/data'), path.join(fixture, 'data'), { recursive: true });
    cpSync(path.join(root, 'artifacts/public/reports'), path.join(fixture, 'reports'), { recursive: true });
    const file = path.join(fixture, 'data/insights.json');
    const insights = JSON.parse(readFileSync(file, 'utf8'));
    const outcome = insights.outcomes[0];
    outcome.status = 'met';
    outcome.report_id = '2026-09-23-evening';
    outcome.observed_date = '2026-09-23';
    outcome.observed_value = 25.4;
    outcome.evidence = [{ report_id: outcome.report_id, section: '六维观察', text: '| 流动性 | 25.4 | 偏弱 | 成交额/历史中位 0.90x |' }];
    writeFileSync(file, JSON.stringify(insights));
    execFileSync('npm', ['run', 'build', '--', '--outDir', path.join(fixture, 'built')], {
      cwd: root, stdio: 'pipe', env: { ...process.env, ASTRO_DATA_ROOT: fixture },
    });
    const html = readFileSync(path.join(fixture, 'built/index.html'), 'utf8');
    assert.match(html, /查看核对依据/);
    assert.match(html, /维度：流动性；观察分：25\.4；状态：偏弱/);
    assert.doesNotMatch(html, /\| 流动性 \|/);
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});
