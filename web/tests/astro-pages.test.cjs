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

test('Astro emits a readable recent-report site with Asian market chart states', () => {
  execFileSync('npm', ['run', 'build'], { cwd: root, stdio: 'pipe' });
  const index = readFileSync(path.join(root, 'dist/index.html'), 'utf8');
  const reports = JSON.parse(readFileSync(path.join(root, 'artifacts/public/data/reports.json'), 'utf8')).reports;
  const reportId = reports[0].id;
  assert.match(index, /Quant 市场情报/);
  assert.ok(index.includes('/quant-intel-platform/'));
  assert.ok(index.includes('href="/quant-intel-platform/docs/"'));
  assert.ok(!index.includes('/market-intel-pages/'));
  assert.match(index, /id="theme-toggle"/);
  assert.match(index, /id="us-session"/);
  assert.match(index, /id="asia-session"/);
  assert.match(index, /07:00 美股收盘复盘/);
  assert.match(index, /19:00 亚洲市场收盘复盘/);
  assert.doesNotMatch(index, /晚报与历史晨报|旧晨报保留归档|id="kind-filter"|id="date-filter"/);
  assert.doesNotMatch(index, /历史亚洲收盘复盘/);
  assert.match(index, /市场驱动/);
  assert.match(index, /阅读全文与数据质量说明/);
  assert.match(index, /核对来源链接/);
  assert.match(index, /id="market-daily-chart"/);
  assert.match(index, /id="asia-daily-chart"/);
  assert.match(index, /id="download-market-chart"/);
  assert.match(index, /id="download-asia-report"/);
  assert.match(index, /Markdown 阅读版/);
  assert.ok(index.indexOf('aria-label="下载这份美股报告"') < index.indexOf('id="market-daily-chart"'));
  const usSection = index.slice(index.indexOf('id="us-session"'), index.indexOf('id="asia-session"'));
  const currentUs = usSection.slice(0, usSection.indexOf('class="market-history"'));
  const usReport = JSON.parse(readFileSync(path.join(root, 'artifacts/public/data/market_daily_report.json'), 'utf8'));
  const usDate = usReport.run_id.slice(6);
  assert.ok(currentUs.includes(`reports/${usDate}-market-daily.md">Markdown 原文`));
  assert.ok(currentUs.includes(`reports/${usDate}-market-daily-no-citations.md">Markdown 阅读版`));
  assert.ok(currentUs.includes(`reports/${usDate}-market-daily.txt">纯文本报告`));
  assert.ok(currentUs.indexOf('Markdown 原文') < currentUs.indexOf('id="market-daily-chart"'));
  assert.ok(currentUs.indexOf('Markdown 阅读版') < currentUs.indexOf('id="market-daily-chart"'));
  assert.ok(currentUs.indexOf('纯文本报告') < currentUs.indexOf('id="market-daily-chart"'));
  assert.doesNotMatch(currentUs, /class="index-grid"|class="market-table"/);
  const chart = index.match(/<div class="market-chart-graphic market-report-graphic" id="market-daily-chart">([\s\S]*?)<\/div>/)?.[1];
  assert.ok(chart);
  assert.match(chart, /市场驱动因素/);
  assert.match(chart, /关键来源/);
  assert.ok(chart.includes(`观测日 ${usDate}`));
  const asia = index.match(/id="asia-daily-chart">([\s\S]*?)<\/div>/)?.[1];
  assert.ok(asia);
  assert.match(asia, /亚洲市场图表/);
  assert.match(asia, /综合盘面/);
  assert.doesNotMatch(asia, /美股隔夜图/);
  assert.match(asia, /数据缺项|缺项/);
  const styles = readdirSync(path.join(root, 'dist/_astro')).filter((name) => name.endsWith('.css'))
    .map((name) => readFileSync(path.join(root, `dist/_astro/${name}`), 'utf8')).join('\n');
  assert.match(styles, /:root\[data-theme=?"?dark/);
  const report = path.join(root, `dist/reports/${reportId}/index.html`);
  assert.ok(existsSync(report));
  const html = readFileSync(report, 'utf8');
  assert.match(html, /id="asia-daily-chart"/);
  assert.match(html, /阅读完整报告与来源/);
  assert.doesNotMatch(html, /data-chart-key="us_overnight"/);
  assert.ok(html.includes(`/quant-intel-platform/reports/${reportId}.md`));
  assert.doesNotMatch(html, /private-chat-target/);
  assert.doesNotMatch(index, /echarts\.|ChartIsland\.|\.png["']/);
  assert.doesNotMatch(html, /echarts\.|ChartIsland\.|\.png["']/);
  assert.match(index, /<a href="https:\/\/home\.treasury\.gov[^"]*"[^>]*>美国财政部<\/a>/);
  assert.doesNotMatch(index, /\| 流动性 \|/);
  assert.match(html, /<table>/);
});

test('new Asian evening reports build a visual history while old direct links remain available', () => {
  const fixture = mkdtempSync(path.join(path.dirname(root), 'modern-evening-history-'));
  try {
    cpSync(path.join(root, 'artifacts/public'), fixture, { recursive: true });
    const indexFile = path.join(fixture, 'data/reports.json');
    const reportIndex = JSON.parse(readFileSync(indexFile, 'utf8'));
    const template = reportIndex.reports.find((row) => row.id === '2026-09-24-evening');
    assert.ok(template);
    for (const date of ['2026-09-28', '2026-09-29']) {
      const id = `${date}-evening`;
      reportIndex.reports.push({ ...template, id, date, title: `收盘复盘（${date}）`,
        source_url: `reports/${id}.md`, generation_mode: 'scheduled' });
      cpSync(path.join(fixture, 'reports/2026-09-24-evening.md'), path.join(fixture, `reports/${id}.md`));
      const chart = JSON.parse(readFileSync(path.join(fixture, 'data/charts/2026-09-24-evening.json'), 'utf8'));
      chart.report_id = id;
      writeFileSync(path.join(fixture, `data/charts/${id}.json`), JSON.stringify(chart));
    }
    writeFileSync(indexFile, JSON.stringify(reportIndex));
    execFileSync('npm', ['run', 'build', '--', '--outDir', path.join(fixture, 'built')], {
      cwd: root, stdio: 'pipe', env: { ...process.env, ASTRO_DATA_ROOT: fixture },
    });
    const home = readFileSync(path.join(fixture, 'built/index.html'), 'utf8');
    assert.match(home, /历史亚洲收盘复盘/);
    assert.match(home, /reports\/2026-09-28-evening\//);
    assert.doesNotMatch(home, /reports\/2026-09-24-morning\//);
    const modern = readFileSync(path.join(fixture, 'built/reports/2026-09-28-evening/index.html'), 'utf8');
    assert.match(modern, /id="asia-daily-chart"/);
    assert.match(modern, /id="download-asia-report"/);
    assert.ok(existsSync(path.join(fixture, 'built/reports/2026-09-24-morning/index.html')));
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
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

test('visual report keeps verified facts, commentary and source links together', () => {
  const index = readFileSync(path.join(root, 'dist/index.html'), 'utf8');
  const chart = index.match(/id="market-daily-chart">([\s\S]*?)<\/div>/)?.[1];
  assert.ok(chart);
  assert.match(chart, /美债收益率水平/);
  assert.match(chart, /\d+\.\d+%/);
  assert.match(chart, /跨资产日涨跌/);
  assert.match(chart, /BTC\/USD 现货/);
  assert.match(chart, /市场驱动因素/);
  assert.match(chart, /关键来源/);
  assert.match(index, /<a href="https:\/\/home\.treasury\.gov[^"]*"[^>]*>美国财政部<\/a>/);
  assert.match(index, /阅读全文与数据质量说明/);
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
  assert.match(index, /数据截至/);
  assert.match(index, /解读生成/);
  if (insight.generation_mode === 'retrospective') assert.match(index, /依据旧报告或补发报告生成/);
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
