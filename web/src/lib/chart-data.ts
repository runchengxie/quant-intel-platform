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
  reason?: string;
}

export interface ChartPayload {
  publication: 'public';
  report_id: string;
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
    && typeof value.source_url === 'string';
}

function isChartPayload(value: unknown, reportId: string): value is ChartPayload {
  return isRecord(value)
    && value.publication === 'public'
    && value.report_id === reportId
    && Array.isArray(value.charts)
    && value.charts.every((card) => isRecord(card)
      && typeof card.title === 'string'
      && typeof card.key === 'string'
      && (card.status === 'ok' || card.status === 'degraded' || card.status === 'missing' || card.status === 'skipped')
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

export function toOption(card: ChartCard): EChartsOption {
  const points = card.points;
  const units = [...new Set(points.map((point) => point.unit))];
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
    yAxis: { type: 'value', name: units.length === 1 ? units[0] : '原始数值（单位见悬停）', axisLine: { show: true } },
    dataZoom: points.length > 8 ? [{ type: 'slider', start: 0, end: Math.min(100, 800 / points.length) }] : [],
    series: [{ name: card.title, type: 'bar', data: points.map((point) => ({
      value: point.value,
      itemStyle: { color: point.value < 0 ? '#5c7182' : '#b64d33' },
    })), markLine: { silent: true, symbol: 'none', data: [{ yAxis: 0 }] } }],
  };
}
