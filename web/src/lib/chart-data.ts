import type {
  EChartsOption,
  TooltipComponentFormatterCallbackParams,
} from 'echarts';

const BASE = '/quant-intel-platform';

export interface ChartPoint {
  label: string;
  value: number;
  unit: string;
  observation_date: string;
  source_label: string;
  source_url: string;
}

export type ChartStatus = 'ok' | 'degraded' | 'missing' | 'skipped';

export interface ChartCard {
  title: string;
  points: ChartPoint[];
  key: string;
  status: ChartStatus;
  reason?: string | null;
}

export interface ChartPayload {
  schema_version: 'market_intel.a_share_charts.v1';
  publication: 'public';
  report_id: string;
  date: string;
  kind: 'morning' | 'evening';
  generated_at: string;
  content_sha256: string;
  charts: ChartCard[];
}

function escapeHtml(value: string | number): string {
  const replacements: Record<string, string> = {
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  };
  return String(value).replace(/[&<>"']/g, (character) => replacements[character]);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function isChartPoint(value: unknown): value is ChartPoint {
  return isRecord(value)
    && typeof value.label === 'string'
    && typeof value.value === 'number'
    && Number.isFinite(value.value)
    && typeof value.unit === 'string'
    && typeof value.observation_date === 'string'
    && typeof value.source_label === 'string'
    && typeof value.source_url === 'string'
    && /^https:\/\//.test(value.source_url);
}

function isChartPayload(value: unknown, reportId: string): value is ChartPayload {
  return isRecord(value)
    && value.schema_version === 'market_intel.a_share_charts.v1'
    && value.publication === 'public'
    && value.report_id === reportId
    && /^\d{4}-\d{2}-\d{2}$/.test(String(value.date))
    && value.date === reportId.slice(0, 10)
    && value.kind === reportId.slice(11)
    && typeof value.generated_at === 'string'
    && !Number.isNaN(Date.parse(value.generated_at))
    && typeof value.content_sha256 === 'string'
    && /^[a-f0-9]{64}$/i.test(value.content_sha256)
    && Array.isArray(value.charts)
    && value.charts.every((card) => isRecord(card)
      && typeof card.title === 'string'
      && typeof card.key === 'string'
      && (card.status === 'ok' || card.status === 'degraded' || card.status === 'missing' || card.status === 'skipped')
      && (card.reason === undefined || card.reason === null || typeof card.reason === 'string')
      && Array.isArray(card.points)
      && card.points.every(isChartPoint));
}

export async function loadChart(reportId: string, fetcher: typeof fetch = fetch): Promise<ChartPayload> {
  if (!/^\d{4}-\d{2}-\d{2}-(?:morning|evening)$/.test(reportId)) {
    throw new Error('invalid chart identity');
  }
  const response = await fetcher(`${BASE}/data/charts/${reportId}.json`);
  if (!response.ok) throw new Error('chart data unavailable');
  const chart = await response.json();
  if (!isChartPayload(chart, reportId)) {
    throw new Error('chart identity mismatch');
  }
  return chart;
}

export function signedValue(value: number, unit: string): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${Math.abs(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} ${unit}`;
}

function axisUnit(unit: string): string {
  return unit.startsWith('观察分') ? '观察分' : unit;
}

export function chartUnits(card: ChartCard): string[] {
  return [...new Set(card.points.map((point) => axisUnit(point.unit)))];
}

export function toOption(card: ChartCard, selectedUnit?: string): EChartsOption {
  const unit = selectedUnit || chartUnits(card)[0];
  const points = card.points.filter((point) => axisUnit(point.unit) === unit);
  return {
    animation: false,
    aria: { enabled: true, description: `${card.title}。逐项数值和来源见图下方表格。` },
    color: ['#b64d33'],
    legend: { show: true, data: [card.title], bottom: 0 },
    grid: { left: 54, right: 30, top: 38, bottom: points.length > 8 ? 96 : 72, containLabel: true },
    tooltip: { trigger: 'item', formatter: (params: TooltipComponentFormatterCallbackParams) => {
      const item = Array.isArray(params) ? params[0] : params;
      const point = points[item.dataIndex ?? 0];
      return `${escapeHtml(point.label)}<br>${escapeHtml(signedValue(point.value, point.unit))}<br>观测日 ${escapeHtml(point.observation_date)}<br>${escapeHtml(point.source_label)}`;
    } },
    xAxis: { type: 'category', data: points.map((point) => point.label), axisLabel: { rotate: points.length > 5 ? 35 : 0, interval: 0 } },
    yAxis: { type: 'value', name: unit, ...(unit === '观察分' ? { min: 0, max: 100 } : {}), axisLine: { show: true } },
    dataZoom: points.length > 8 ? [{ type: 'slider', start: 0, end: Math.min(100, 800 / points.length) }] : [],
    series: [{ name: card.title, type: 'bar', data: points.map((point) => ({
      value: point.value,
      itemStyle: { color: point.value < 0 ? '#5c7182' : '#b64d33' },
    })), markLine: { silent: true, symbol: 'none', data: [{ yAxis: 0 }] } }],
  };
}
