import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import type { ChartCard, ChartStatus } from './chart-data.ts';

export const CHART_KEYS = ['dashboard', 'moneyflow', 'topic', 'sentiment', 'us_overnight', 'weekly_chart'] as const;
export type ChartKey = typeof CHART_KEYS[number];
export const VISUAL_REPORT_START_DATE = '2026-09-28';
export const CHART_TITLES: Record<ChartKey, string> = {
  dashboard: '综合仪表盘', moneyflow: '资金流向图', topic: '热点概念图',
  sentiment: '情绪指标图', us_overnight: '美股隔夜图', weekly_chart: '周度概览图',
};

export type JsonRecord = Record<string, unknown>;
export type ReportRecord = JsonRecord & { id: string; date: string; kind: string; source_url: string; publication?: string };
export type SummaryRecord = JsonRecord & { date: string };
export type MarketDailyRecord = JsonRecord & { run_id: string; publication?: string };

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isReportRecord(value: unknown): value is ReportRecord {
  return isRecord(value) && typeof value.id === 'string' && typeof value.date === 'string'
    && typeof value.kind === 'string' && typeof value.source_url === 'string';
}

export function dataRoot(): string {
  return path.resolve(process.env.ASTRO_DATA_ROOT || path.join(process.cwd(), 'artifacts/public'));
}

export function readJson(relativePath: string): unknown {
  const file = path.join(dataRoot(), relativePath);
  if (!existsSync(file)) return null;
  return JSON.parse(readFileSync(file, 'utf8')) as unknown;
}

export function loadReports(): ReportRecord[] {
  const index = readJson('data/reports.json');
  if (!isRecord(index) || index.schema_version !== 'market_intel_pages.reports.v1' || !Array.isArray(index.reports)) {
    throw new Error('invalid public report index');
  }
  const reports = index.reports.filter(isReportRecord);
  const dates = [...new Set(reports.map((row) => row.date))].sort().reverse().slice(0, 5);
  return reports.filter((row) => dates.includes(row.date)).sort((a, b) =>
    b.date.localeCompare(a.date) || a.kind.localeCompare(b.kind));
}

export function loadChart(reportId: string): ChartCard[] {
  if (!/^\d{4}-\d{2}-\d{2}-(?:morning|evening)$/.test(reportId)) throw new Error('invalid chart identity');
  const chart = readJson(`data/charts/${reportId}.json`);
  if (chart && !isPublicChartPayload(chart, reportId)) throw new Error('unreviewed or mismatched chart file');
  return isRecord(chart) && Array.isArray(chart.charts) && chart.charts.every(isChartCard) ? chart.charts : CHART_KEYS.map((key) => ({
    key, title: key === 'sentiment' && reportId.endsWith('-evening') ? '市场温度计' : CHART_TITLES[key],
    status: 'missing' as const, reason: '尚无通过逐点审核的公开图表数据', points: [],
  }));
}

function isChartCard(value: unknown): value is ChartCard {
  return isRecord(value) && typeof value.key === 'string' && typeof value.title === 'string'
    && isChartStatus(value.status)
    && (value.reason === undefined || value.reason === null || typeof value.reason === 'string')
    && Array.isArray(value.points) && value.points.every((point) => isRecord(point)
      && typeof point.label === 'string' && typeof point.value === 'number' && Number.isFinite(point.value)
      && typeof point.unit === 'string' && typeof point.observation_date === 'string'
      && /^\d{4}-\d{2}-\d{2}$/.test(point.observation_date) && typeof point.source_label === 'string'
      && typeof point.source_url === 'string' && /^https:\/\//.test(point.source_url));
}

function isChartStatus(value: unknown): value is ChartStatus {
  return value === 'ok' || value === 'degraded' || value === 'missing' || value === 'skipped';
}

function isPublicChartPayload(chart: unknown, reportId: string): boolean {
  if (!isRecord(chart)) return false;
  return chart.schema_version === 'market_intel.a_share_charts.v1' && chart.publication === 'public'
    && chart.report_id === reportId && chart.date === reportId.slice(0, 10) && chart.kind === reportId.slice(11)
    && typeof chart.generated_at === 'string' && !Number.isNaN(Date.parse(chart.generated_at))
    && typeof chart.content_sha256 === 'string' && /^[a-f0-9]{64}$/i.test(chart.content_sha256)
    && Array.isArray(chart.charts) && chart.charts.every(isChartCard);
}

export function loadMarkdown(report: ReportRecord): string {
  if (report.source_url !== `reports/${report.id}.md`) throw new Error('report Markdown path mismatch');
  return readFileSync(path.join(dataRoot(), report.source_url), 'utf8');
}

export function loadSummaries(reports: ReportRecord[]): SummaryRecord[] {
  const allowed = new Set(reports.map((row) => row.id));
  const payload = readJson('data/daily_summaries.json');
  const summaries = isRecord(payload) && Array.isArray(payload.summaries)
    ? payload.summaries.filter((row): row is SummaryRecord => isRecord(row) && typeof row.date === 'string') : [];
  return summaries.filter((row) => allowed.has(String(row.morning_report_id)) && allowed.has(String(row.evening_report_id)));
}

export function loadMarketDaily(): MarketDailyRecord & { date: string; markdown: string | null; hasCitationFreeMarkdown: boolean } | null {
  const value = readJson('data/market_daily_report.json');
  if (!isRecord(value) || typeof value.run_id !== 'string' || !/^daily-\d{4}-\d{2}-\d{2}$/.test(value.run_id)) return null;
  return withMarketDailyFiles(value as MarketDailyRecord);
}

function withMarketDailyFiles(report: MarketDailyRecord): MarketDailyRecord & { date: string; markdown: string | null; hasCitationFreeMarkdown: boolean } {
  const date = report.run_id.slice(6);
  const file = path.join(dataRoot(), `reports/${date}-market-daily.md`);
  const reading = path.join(dataRoot(), `reports/${date}-market-daily-no-citations.md`);
  return { ...report, date, markdown: existsSync(file) ? readFileSync(file, 'utf8') : null, hasCitationFreeMarkdown: existsSync(reading) };
}

export function loadMarketDailyHistory(): Array<MarketDailyRecord & { date: string; markdown: string; hasCitationFreeMarkdown: boolean }> {
  const history = readJson('data/market_daily_reports.json');
  const historyRows = isRecord(history) && history.schema_version === 'market_intel_pages.us_daily_history.v1'
    && Array.isArray(history.reports) ? history.reports : [];
  const fallback = loadMarketDaily();
  const rows = historyRows.length ? historyRows : fallback ? [fallback] : [];
  return rows.filter((row): row is MarketDailyRecord => isRecord(row) && typeof row.run_id === 'string'
    && row.publication === 'public' && /^daily-\d{4}-\d{2}-\d{2}$/.test(row.run_id))
    .slice(0, 5).map((row) => withMarketDailyFiles(row as MarketDailyRecord))
    .filter((row): row is MarketDailyRecord & { date: string; markdown: string; hasCitationFreeMarkdown: boolean } => row.markdown !== null);
}

export function loadLatestInsight(): JsonRecord | null {
  const value = readJson('data/insights.json');
  const history = isRecord(value) && Array.isArray(value.insights) ? value.insights.filter(isRecord) : [];
  return history.sort((a, b) => String(b.date).localeCompare(String(a.date)))[0] || null;
}
