const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync, existsSync, cpSync, writeFileSync, mkdtempSync, rmSync, readdirSync } = require('node:fs');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..');

function assertDriverSectionMatchesReport(chart, report) {
  const hasVerifiedDrivers = report.sections?.some((section) => section.key === 'drivers' && section.claims?.length);
  if (hasVerifiedDrivers) assert.match(chart, /市场驱动因素/);
  else assert.doesNotMatch(chart, /市场驱动因素/);
}

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

test('public locale contract defaults the root entry to English and keeps Chinese explicit', () => {
  const locale = readFileSync(path.join(root, 'src/lib/locale.ts'), 'utf8');
  const home = readFileSync(path.join(root, 'src/pages/index.astro'), 'utf8');
  assert.match(locale, /'en-US': '\/en\/'/);
  assert.match(locale, /'zh-CN': '\/\?locale=zh-CN'/);
  assert.match(home, /get\('locale'\) !== 'zh-CN'/);
  assert.match(home, /new URL\('en\/', document\.baseURI\)/);
});

test('Astro emits a readable recent-report site with Asian market chart states', () => {
  const chartCards = readFileSync(path.join(root, 'src/components/ChartCards.astro'), 'utf8');
  assert.match(chartCards, /ChartIsland\.tsx/);
  execFileSync('npm', ['run', 'build'], { cwd: root, stdio: 'pipe' });
  const index = readFileSync(path.join(root, 'dist/index.html'), 'utf8');
  const reports = JSON.parse(readFileSync(path.join(root, 'artifacts/public/data/reports.json'), 'utf8')).reports;
  const latestEvening = reports.filter((row) => row.kind === 'evening').sort((a, b) => b.date.localeCompare(a.date))[0];
  assert.match(index, /Quant 市场情报/);
  assert.ok(index.includes('/quant-intel-platform/'));
  assert.ok(index.includes('href="/quant-intel-platform/docs/"'));
  assert.ok(!index.includes('/market-intel-pages/'));
  assert.match(index, /id="theme-toggle"/);
  const english = readFileSync(path.join(root, 'dist/en/index.html'), 'utf8');
  assert.match(english, /<button[^>]*id="theme-toggle"[^>]*aria-pressed="false"[^>]*>Dark mode<\/button>/);
  assert.match(english, /aria-label="Switch to dark mode"/);
  assert.doesNotMatch(english, /亚洲市场收盘复盘|目标日期|六维观察|市场状态/);
  assert.match(english, /Asia market close review|Target date|Six-dimension observation|Market state/);
  assert.match(english.slice(0, english.indexOf('</head>')), /market-intel-theme/, 'English theme is initialized before body paint');
  const header = index.match(/<header class="topbar">([\s\S]*?)<\/header>/)?.[1];
  assert.ok(header);
  assert.match(header, /<nav class="top-nav"[^>]*><a href="#us-session">美股日报<\/a><a href="#asia-session">亚洲晚报<\/a>/);
  assert.match(header, /<a href="\/quant-intel-platform\/docs\/">文档<\/a>/);
  assert.match(header, /<button[^>]*id="theme-toggle"[^>]*aria-pressed="false"[^>]*>深色模式<\/button>/);
  assert.match(index, /id="us-session"/);
  assert.match(index, /id="asia-session"/);
  assert.match(index, /07:00 美股收盘复盘/);
  assert.match(index, /19:00 亚洲市场收盘复盘/);
  assert.doesNotMatch(index, /晚报与历史晨报|旧晨报保留归档|id="kind-filter"|id="date-filter"/);
  const latestEveningDate = reports.filter((row) => row.kind === 'evening').map((row) => row.date).sort().at(-1);
  const hasVisualHistory = reports.some((row) => row.kind === 'evening' && row.date >= '2026-09-25' && row.date < latestEveningDate);
  if (hasVisualHistory) assert.match(index, /历史亚洲收盘复盘/);
  else assert.doesNotMatch(index, /历史亚洲收盘复盘/);
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
  assert.ok(currentUs.includes(`data-report-content-hash="${usReport.content_hash}"`));
  assert.ok(currentUs.includes(`reports/${usDate}-market-daily.md">Markdown 原文`));
  assert.ok(currentUs.includes(`reports/${usDate}-market-daily-no-citations.md">Markdown 阅读版`));
  assert.ok(currentUs.includes(`reports/${usDate}-market-daily.txt">纯文本报告`));
  assert.ok(currentUs.indexOf('Markdown 原文') < currentUs.indexOf('id="market-daily-chart"'));
  assert.ok(currentUs.indexOf('Markdown 阅读版') < currentUs.indexOf('id="market-daily-chart"'));
  assert.ok(currentUs.indexOf('纯文本报告') < currentUs.indexOf('id="market-daily-chart"'));
  assert.doesNotMatch(currentUs, /class="index-grid"|class="market-table"/);
  const chart = index.match(/<div class="market-chart-graphic market-report-graphic" id="market-daily-chart">([\s\S]*?)<\/div>/)?.[1];
  assert.ok(chart);
  assertDriverSectionMatchesReport(chart, usReport);
  assert.match(chart, /关键来源/);
  assert.ok(chart.includes(`观测日 ${usDate}`));
  const asia = index.match(/id="asia-daily-chart">([\s\S]*?)<\/div>/)?.[1];
  const eveningHash = execFileSync('python', ['-c', 'import hashlib,json,sys; row=json.load(sys.stdin); print(hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest())'], {
    input: JSON.stringify(latestEvening), encoding: 'utf8',
  }).trim();
  assert.ok(index.includes(`data-report-content-hash="${eveningHash}"`));
  assert.ok(asia);
  const eveningMarkdown = readFileSync(path.join(root, 'artifacts/public', latestEvening.source_url), 'utf8');
  const holiday = eveningMarkdown.includes('## 亚洲市场收盘复盘（');
  const reportId = holiday ? latestEvening.id : reports[0].id;
  if (holiday) {
    assert.match(asia, /亚洲市场收盘复盘/);
    assert.match(asia, /data-table="asia-sessions"/);
    assert.match(asia, /A 股今日休市/);
    assert.doesNotMatch(asia, /综合盘面/);
  } else {
    assert.match(asia, /亚洲市场图表/);
    assert.match(asia, /综合盘面/);
  }
  assert.doesNotMatch(asia, /美股隔夜图/);
  assert.match(asia, /数据缺项|缺项/);
  const styles = readdirSync(path.join(root, 'dist/_astro')).filter((name) => name.endsWith('.css'))
    .map((name) => readFileSync(path.join(root, `dist/_astro/${name}`), 'utf8')).join('\n');
  assert.match(styles, /:root\[data-theme=?"?dark/);
  const topNavRules = [...styles.matchAll(/\.top-nav\{([^}]*)\}/g)].map((match) => match[1]);
  const homeTopNav = topNavRules.find((rule) => rule.includes('margin-right:40px'));
  assert.ok(homeTopNav, 'compiled home site has top navigation styles');
  assert.ok(Number(homeTopNav.match(/gap:(\d+)px/)?.[1]) >= 36, 'top navigation links have generous spacing');
  assert.ok(Number(homeTopNav.match(/margin-right:(\d+)px/)?.[1]) >= 40, 'navigation has space before the theme button');
  assert.match(homeTopNav, /flex-shrink:0/);
  const report = path.join(root, `dist/reports/${reportId}/index.html`);
  assert.ok(existsSync(report));
  assert.ok(existsSync(path.join(root, 'dist/404.html')));
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

test('English report pages translate source-language presentation text', () => {
  execFileSync('npm', ['run', 'build'], { cwd: root, stdio: 'pipe' });
  const englishReport = readFileSync(path.join(root, 'dist/en/reports/2026-09-29-evening/index.html'), 'utf8');
  assert.doesNotMatch(englishReport, /亚洲市场收盘复盘|六维观察|热门概念|市场状态/);
  assert.match(englishReport, /Asia market close review|Six-dimension observation|Hot concepts|Market state/);
});

test('English homepage includes every reviewed research source link', () => {
  execFileSync('npm', ['run', 'build'], { cwd: root, stdio: 'pipe' });
  const html = readFileSync(path.join(root, 'dist/en/index.html'), 'utf8');
  const report = JSON.parse(readFileSync(path.join(root, 'artifacts/public/data/market_daily_report.json'), 'utf8'));
  const sourceBlock = html.match(/<details class="secondary-report market-sources">([\s\S]*?)<\/details>/)?.[1];
  assert.ok(sourceBlock);
  for (const href of new Set(report.claims.flatMap((claim) => claim.sources))) {
    const escaped = href.replaceAll('&', '&amp;');
    assert.ok(sourceBlock.includes(`href="${escaped}"`), `Missing reviewed research citation: ${href}`);
    assert.equal(sourceBlock.split(`href="${escaped}"`).length - 1, 1, 'Source links are deduplicated');
  }
});

test('English homepage exposes dated PNG controls and recent U.S. history', () => {
  execFileSync('npm', ['run', 'build'], { cwd: root, stdio: 'pipe' });
  const html = readFileSync(path.join(root, 'dist/en/index.html'), 'utf8');
  const report = JSON.parse(readFileSync(path.join(root, 'artifacts/public/data/market_daily_report.json'), 'utf8'));
  const date = report.run_id.slice(6);
  assert.match(html, /id="download-market-chart"/);
  assert.match(html, /id="download-asia-report"/);
  assert.ok(html.includes(`data-report-date="${date}" data-report-kind="market-daily" data-report-content-hash="${report.content_hash}"`));
  assert.match(html, /data-chart-target="#market-daily-chart svg"/);
  assert.match(html, /data-chart-target="#asia-daily-chart svg"/);
  const generated = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(report.as_of));
  assert.ok(html.includes(generated));
  assert.match(html, /America\/New_York/);
  assert.match(html, /Recent U\.S\. reports/);
  const history = JSON.parse(readFileSync(path.join(root, 'artifacts/public/data/market_daily_reports.json'), 'utf8'));
  for (const row of history.reports.filter((row) => row.run_id.slice(6) >= '2026-09-28' && row.run_id !== report.run_id)) {
    assert.ok(html.includes(`id="market-history-chart-${row.run_id.slice(6)}"`));
  }
});

test('English home uses the same report sections and responsive shell as Chinese home', () => {
  const english = readFileSync(path.join(root, 'src/pages/en/index.astro'), 'utf8');
  for (const marker of ['class="shell"', 'class="session-nav"', 'id="us-session"', 'id="asia-session"', 'id="market-daily-chart"', 'id="asia-daily-chart"', 'class="reports-section"']) {
    assert.ok(english.includes(marker), `English home is missing ${marker}`);
  }
  assert.match(english, /<html lang="en-US">/);
  assert.match(english, /U\.S\. market close review/);
  assert.match(english, /Asia market close review/);
});

test('home theme button keeps a stable label, toggles both ways, and restores the saved choice', () => {
  const source = readFileSync(path.join(root, 'src/pages/index.astro'), 'utf8');
  const script = source.match(/<script>\s*([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script, 'home theme controller exists');
  const saved = new Map();
  const storage = {
    getItem: (key) => saved.get(key) ?? null,
    setItem: (key, value) => saved.set(key, value),
  };
  const load = (localStorage) => {
    const events = {};
    const attrs = {};
    const button = {
      textContent: '深色模式',
      setAttribute: (name, value) => { attrs[name] = value; },
      addEventListener: (name, handler) => { events[name] = handler; },
    };
    const document = {
      documentElement: { dataset: {} },
      querySelector: () => button,
      querySelectorAll: () => [],
    };
    vm.runInNewContext(script, { document, localStorage, window: {
      matchMedia: () => ({ matches: false, addEventListener: () => {} }),
    } });
    return { button, attrs, events, document };
  };
  const page = load(storage);
  assert.equal(page.document.documentElement.dataset.theme, 'light');
  assert.equal(page.attrs['aria-pressed'], 'false');
  page.events.click();
  assert.equal(page.document.documentElement.dataset.theme, 'dark');
  assert.equal(page.attrs['aria-pressed'], 'true');
  assert.equal(page.button.textContent, '深色模式');
  assert.equal(storage.getItem('market-intel-theme'), 'dark');
  const reloaded = load(storage);
  assert.equal(reloaded.document.documentElement.dataset.theme, 'dark');
  assert.equal(reloaded.attrs['aria-pressed'], 'true');
  reloaded.events.click();
  assert.equal(reloaded.document.documentElement.dataset.theme, 'light');
  assert.equal(storage.getItem('market-intel-theme'), 'light');
});

test('home theme remains usable when browser storage is unavailable', () => {
  const source = readFileSync(path.join(root, 'src/pages/index.astro'), 'utf8');
  const script = source.match(/<script>\s*([\s\S]*?)<\/script>/)?.[1];
  const events = {};
  const document = {
    documentElement: { dataset: { theme: 'light' } },
    querySelector: () => ({ setAttribute: () => {}, addEventListener: (name, handler) => { events[name] = handler; } }),
    querySelectorAll: () => [],
  };
  const localStorage = { getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); } };
  assert.doesNotThrow(() => vm.runInNewContext(script, { document, localStorage, window: {
    matchMedia: () => ({ matches: false, addEventListener: () => {} }),
  } }));
  assert.doesNotThrow(() => events.click());
  assert.equal(document.documentElement.dataset.theme, 'dark');
});

test('English entry restores theme and keeps its button synchronized when storage is denied or OS theme changes', () => {
  const source = readFileSync(path.join(root, 'src/pages/en/index.astro'), 'utf8');
  const head = source.match(/<head>([\s\S]*?)<\/head>/)?.[1];
  const bootstrap = head?.match(/<script is:inline>\s*([\s\S]*?)<\/script>/)?.[1];
  const header = source.match(/<header class="topbar">([\s\S]*?)<\/header>/)?.[1];
  const initialButtonSync = header?.match(/<script is:inline>\s*([\s\S]*?)<\/script>/)?.[1];
  const controller = source.match(/<script>\s*([\s\S]*?)<\/script>/)?.[1];
  assert.ok(bootstrap, 'English pre-paint theme bootstrap exists');
  assert.ok(initialButtonSync, 'English button state is synchronized as the header parses');
  assert.ok(controller, 'English theme controller exists');
  const run = ({ stored = null, denied = false, dark = false } = {}) => {
    const rootElement = { dataset: {} };
    const attrs = { 'aria-pressed': 'false', 'aria-label': 'Switch to dark mode' };
    const events = {};
    const mediaEvents = {};
    const button = {
      textContent: 'Dark mode',
      setAttribute: (name, value) => { attrs[name] = value; },
      addEventListener: (name, handler) => { events[name] = handler; },
    };
    const media = {
      matches: dark,
      addEventListener: (name, handler) => { mediaEvents[name] = handler; },
    };
    const localStorage = {
      getItem: (key) => {
        assert.equal(key, 'market-intel-theme');
        if (denied) throw new Error('blocked');
        return stored;
      },
      setItem: (key, value) => {
        assert.equal(key, 'market-intel-theme');
        if (denied) throw new Error('blocked');
        stored = value;
      },
    };
    const document = { documentElement: rootElement, querySelector: () => button };
    const window = { matchMedia: () => media };
    vm.runInNewContext(bootstrap, { document, localStorage, matchMedia: window.matchMedia });
    const beforeController = rootElement.dataset.theme;
    vm.runInNewContext(initialButtonSync, { document });
    const buttonBeforeController = { ...attrs };
    vm.runInNewContext(controller, { document, localStorage, window });
    return { rootElement, attrs, events, mediaEvents, media, button, beforeController, buttonBeforeController, saved: () => stored };
  };
  const restored = run({ stored: 'dark' });
  assert.equal(restored.beforeController, 'dark');
  assert.equal(restored.buttonBeforeController['aria-pressed'], 'true');
  assert.equal(restored.buttonBeforeController['aria-label'], 'Switch to light mode');
  assert.equal(restored.attrs['aria-pressed'], 'true');
  assert.equal(restored.attrs['aria-label'], 'Switch to light mode');
  restored.media.matches = false;
  restored.mediaEvents.change();
  assert.equal(restored.rootElement.dataset.theme, 'dark');
  assert.equal(restored.attrs['aria-pressed'], 'true');
  restored.events.click();
  assert.equal(restored.rootElement.dataset.theme, 'light');
  assert.equal(restored.attrs['aria-pressed'], 'false');
  assert.equal(restored.attrs['aria-label'], 'Switch to dark mode');
  assert.equal(restored.button.textContent, 'Dark mode');
  assert.equal(restored.saved(), 'light');
  const invalid = run({ stored: 'sepia' });
  assert.equal(invalid.beforeController, 'light');
  invalid.media.matches = true;
  invalid.mediaEvents.change();
  assert.equal(invalid.rootElement.dataset.theme, 'dark');
  assert.equal(invalid.attrs['aria-pressed'], 'true');
  assert.equal(invalid.attrs['aria-label'], 'Switch to light mode');
  const denied = run({ denied: true });
  assert.equal(denied.beforeController, 'light');
  denied.events.click();
  assert.equal(denied.rootElement.dataset.theme, 'dark');
  assert.equal(denied.attrs['aria-pressed'], 'true');
  assert.equal(denied.attrs['aria-label'], 'Switch to light mode');
  denied.media.matches = true;
  denied.mediaEvents.change();
  assert.equal(denied.rootElement.dataset.theme, 'dark');
  assert.equal(denied.attrs['aria-pressed'], 'true');
  denied.media.matches = false;
  denied.mediaEvents.change();
  assert.equal(denied.rootElement.dataset.theme, 'light');
  assert.equal(denied.attrs['aria-pressed'], 'false');
  assert.equal(denied.attrs['aria-label'], 'Switch to dark mode');
  denied.events.click();
  assert.equal(denied.rootElement.dataset.theme, 'dark');
  assert.equal(denied.attrs['aria-pressed'], 'true');
  assert.equal(denied.attrs['aria-label'], 'Switch to light mode');
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
      chart.date = date;
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

test('US daily macro-only edition keeps economic data without inventing market charts', () => {
  const fixture = mkdtempSync(path.join(path.dirname(root), 'market-daily-empty-chart-'));
  try {
    cpSync(path.join(root, 'artifacts/public/data'), path.join(fixture, 'data'), { recursive: true });
    cpSync(path.join(root, 'artifacts/public/reports'), path.join(fixture, 'reports'), { recursive: true });
    const file = path.join(fixture, 'data/market_daily_report.json');
    const report = JSON.parse(readFileSync(path.join(__dirname, 'fixtures/market-daily-complete.json'), 'utf8'));
    report.facts = report.facts.filter((fact) => fact.id.startsWith('macro.'));
    report.claims = [];
    report.source_status.equities = { quality: 'missing' };
    writeFileSync(file, JSON.stringify(report));
    writeFileSync(path.join(fixture, 'data/market_daily_reports.json'), JSON.stringify({ schema_version: 'market_intel_pages.us_daily_history.v1', reports: [report] }));
    execFileSync('npm', ['run', 'build', '--', '--outDir', path.join(fixture, 'built')], {
      cwd: root, stdio: 'pipe', env: { ...process.env, ASTRO_DATA_ROOT: fixture },
    });
    const html = readFileSync(path.join(fixture, 'built/index.html'), 'utf8');
    const chart = html.match(/id="market-daily-chart">([\s\S]*?)<\/div>/)?.[1];
    assert.ok(chart);
    assert.match(chart, /经济数据|CPI 同比/);
    assert.doesNotMatch(chart, /四大指数收盘涨跌|美股个股日涨跌|美债收益率水平|美债收益率当日变动|跨资产日涨跌|BTC\/USD/);
    assert.match(html, /id="download-market-chart"/);
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});

test('visual report keeps verified market facts and source links together', () => {
  const fixture = mkdtempSync(path.join(path.dirname(root), 'market-daily-complete-chart-'));
  try {
    cpSync(path.join(root, 'artifacts/public/data'), path.join(fixture, 'data'), { recursive: true });
    cpSync(path.join(root, 'artifacts/public/reports'), path.join(fixture, 'reports'), { recursive: true });
    const report = JSON.parse(readFileSync(path.join(__dirname, 'fixtures/market-daily-complete.json'), 'utf8'));
    writeFileSync(path.join(fixture, 'data/market_daily_report.json'), JSON.stringify(report));
    writeFileSync(path.join(fixture, 'data/market_daily_reports.json'), JSON.stringify({ schema_version: 'market_intel_pages.us_daily_history.v1', reports: [report] }));
    execFileSync('npm', ['run', 'build', '--', '--outDir', path.join(fixture, 'built')], {
      cwd: root, stdio: 'pipe', env: { ...process.env, ASTRO_DATA_ROOT: fixture },
    });
    const index = readFileSync(path.join(fixture, 'built/index.html'), 'utf8');
    const chart = index.match(/id="market-daily-chart">([\s\S]*?)<\/div>/)?.[1];
    assert.ok(chart);
    assert.match(chart, /美债收益率水平/);
    const twoYear = report.facts.find((fact) => fact.id === 'treasury.2y.level_percent');
    assert.ok(twoYear);
    const twoYearSection = chart.slice(chart.indexOf('2 年期美债收益率水平'));
    assert.ok(twoYearSection.slice(0, 600).includes(`${twoYear.value.toFixed(2)}%`));
    assert.match(chart, /跨资产日涨跌/);
    assert.match(chart, /BTC\/USD 现货/);
    assertDriverSectionMatchesReport(chart, report);
    assert.match(chart, /关键来源/);
    assert.match(index, /<a href="https:\/\/home\.treasury\.gov[^"]*"[^>]*>美国财政部<\/a>/);
    assert.match(index, /阅读全文与数据质量说明/);
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
  const { renderMarkdown } = await import('../src/lib/markdown.ts');
  const html = renderMarkdown('| 维度 | 值 |\n|---|---:|\n| 流动性 | 17.1 |\n\n<script>alert(1)</script>\n[bad](javascript:alert(1))');
  assert.match(html, /<table>/);
  assert.match(html, /流动性/);
  assert.doesNotMatch(html, /<script|href="javascript:/);
});

test('market daily source URLs become compact numbered links only in the rendered page', async () => {
  const { renderMarkdown } = await import('../src/lib/markdown.ts');
  const source = '- 来源：https://example.com/one, https://example.org/two';
  const html = renderMarkdown(source, { compactSources: true });
  assert.match(html, /<a href="https:\/\/example.com\/one"[^>]*>来源1<\/a>/);
  assert.match(html, /<a href="https:\/\/example.org\/two"[^>]*>来源2<\/a>/);
  assert.doesNotMatch(html, />https:\/\/example.com\/one</);
  assert.match(renderMarkdown(source), /https:\/\/example.com\/one/);
});

test('single table-row evidence is labelled instead of showing raw Markdown pipes', async () => {
  const { formatEvidenceLine } = await import('../src/lib/evidence.ts');
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
