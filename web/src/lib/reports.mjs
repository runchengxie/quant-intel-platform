import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';

export const CHART_KEYS = ['dashboard', 'moneyflow', 'topic', 'sentiment', 'us_overnight', 'weekly_chart'];
export const VISUAL_REPORT_START_DATE = '2026-09-28';
export const CHART_TITLES = {
  dashboard: '综合仪表盘', moneyflow: '资金流向图', topic: '热点概念图',
  sentiment: '情绪指标图', us_overnight: '美股隔夜图', weekly_chart: '周度概览图',
};

export function dataRoot() {
  return path.resolve(process.env.ASTRO_DATA_ROOT || path.join(process.cwd(), 'artifacts/public'));
}

export function readJson(relativePath) {
  const file = path.join(dataRoot(), relativePath);
  if (!existsSync(file)) return null;
  return JSON.parse(readFileSync(file, 'utf8'));
}

export function loadReports() {
  const index = readJson('data/reports.json');
  if (index?.schema_version !== 'market_intel_pages.reports.v1' || !Array.isArray(index.reports)) {
    throw new Error('invalid public report index');
  }
  const dates = [...new Set(index.reports.map((row) => row.date))].sort().reverse().slice(0, 5);
  return index.reports.filter((row) => dates.includes(row.date)).sort((a, b) =>
    b.date.localeCompare(a.date) || a.kind.localeCompare(b.kind));
}

export function loadChart(reportId) {
  if (!/^\d{4}-\d{2}-\d{2}-(?:morning|evening)$/.test(reportId)) throw new Error('invalid chart identity');
  const chart = readJson(`data/charts/${reportId}.json`);
  if (chart && !isPublicChartPayload(chart, reportId)) {
    throw new Error('unreviewed or mismatched chart file');
  }
  return chart?.charts || CHART_KEYS.map((key) => ({
    key,
    title: key === 'sentiment' && reportId.endsWith('-evening') ? '市场温度计' : CHART_TITLES[key],
    status: 'missing',
    reason: '尚无通过逐点审核的公开图表数据',
    points: [],
  }));
}

function isPublicChartPayload(chart, reportId) {
  return chart?.schema_version === 'market_intel.a_share_charts.v1'
    && chart.publication === 'public'
    && chart.report_id === reportId
    && chart.date === reportId.slice(0, 10)
    && chart.kind === reportId.slice(11)
    && typeof chart.generated_at === 'string'
    && !Number.isNaN(Date.parse(chart.generated_at))
    && typeof chart.content_sha256 === 'string'
    && /^[a-f0-9]{64}$/i.test(chart.content_sha256)
    && Array.isArray(chart.charts)
    && chart.charts.every((card) => card && typeof card.key === 'string'
      && typeof card.title === 'string'
      && ['ok', 'degraded', 'missing', 'skipped'].includes(card.status)
      && (card.reason === undefined || card.reason === null || typeof card.reason === 'string')
      && Array.isArray(card.points)
      && card.points.every((point) => point && typeof point.label === 'string'
        && typeof point.value === 'number' && Number.isFinite(point.value)
        && typeof point.unit === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(point.observation_date)
        && typeof point.source_label === 'string' && /^https:\/\//.test(point.source_url)));
}

export function loadMarkdown(report) {
  const relativePath = report.source_url;
  if (relativePath !== `reports/${report.id}.md`) throw new Error('report Markdown path mismatch');
  return readFileSync(path.join(dataRoot(), relativePath), 'utf8');
}

export function loadSummaries(reports) {
  const allowed = new Set(reports.map((row) => row.id));
  return (readJson('data/daily_summaries.json')?.summaries || []).filter((row) =>
    allowed.has(row.morning_report_id) && allowed.has(row.evening_report_id));
}

export function loadMarketDaily() {
  const report = readJson('data/market_daily_report.json');
  if (!report || !/^daily-\d{4}-\d{2}-\d{2}$/.test(report.run_id)) return null;
  const date = report.run_id.slice(6);
  const file = path.join(dataRoot(), `reports/${date}-market-daily.md`);
  const reading = path.join(dataRoot(), `reports/${date}-market-daily-no-citations.md`);
  return { ...report, date, markdown: existsSync(file) ? readFileSync(file, 'utf8') : null,
    hasCitationFreeMarkdown: existsSync(reading) };
}

export function loadMarketDailyHistory() {
  const history = readJson('data/market_daily_reports.json');
  const rows = history?.schema_version === 'market_intel_pages.us_daily_history.v1'
    && Array.isArray(history.reports) ? history.reports : [readJson('data/market_daily_report.json')].filter(Boolean);
  return rows.filter((row) => row.publication === 'public' && /^daily-\d{4}-\d{2}-\d{2}$/.test(row.run_id))
    .slice(0, 5).map((row) => {
      const date = row.run_id.slice(6);
      const file = path.join(dataRoot(), `reports/${date}-market-daily.md`);
      const reading = path.join(dataRoot(), `reports/${date}-market-daily-no-citations.md`);
      return { ...row, date, markdown: existsSync(file) ? readFileSync(file, 'utf8') : null,
        hasCitationFreeMarkdown: existsSync(reading) };
    }).filter((row) => row.markdown);
}

export function loadLatestInsight() {
  const history = readJson('data/insights.json')?.insights || [];
  return [...history].sort((a, b) => b.date.localeCompare(a.date))[0] || null;
}
