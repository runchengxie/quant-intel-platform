const BASE = '/quant-intel-platform';

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
}

export async function loadChart(reportId, fetcher = fetch) {
  if (!/^\d{4}-\d{2}-\d{2}-(?:morning|evening)$/.test(reportId)) {
    throw new Error('invalid chart identity');
  }
  const response = await fetcher(`${BASE}/data/charts/${reportId}.json`);
  if (!response.ok) throw new Error('chart data unavailable');
  const chart = await response.json();
  if (chart.publication !== 'public' || chart.report_id !== reportId || !Array.isArray(chart.charts)) {
    throw new Error('chart identity mismatch');
  }
  return chart;
}

export function signedValue(value, unit) {
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${Math.abs(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} ${unit}`;
}

export function toOption(card) {
  const points = card.points;
  const units = [...new Set(points.map((point) => point.unit))];
  return {
    animation: false,
    aria: { enabled: true, description: `${card.title}。逐项数值和来源见图下方表格。` },
    color: ['#b3513b'],
    legend: { show: true, data: [card.title], bottom: 0 },
    grid: { left: 54, right: 30, top: 38, bottom: points.length > 8 ? 96 : 72, containLabel: true },
    tooltip: { trigger: 'item', formatter: (params) => {
      const point = points[params.dataIndex];
      return `${escapeHtml(point.label)}<br>${escapeHtml(signedValue(point.value, point.unit))}<br>观测日 ${escapeHtml(point.observation_date)}<br>${escapeHtml(point.source_label)}`;
    } },
    xAxis: { type: 'category', data: points.map((point) => point.label), axisLabel: { rotate: points.length > 5 ? 35 : 0, interval: 0 } },
    yAxis: { type: 'value', name: units.length === 1 ? units[0] : '原始数值（单位见悬停）', axisLine: { show: true } },
    dataZoom: points.length > 8 ? [{ type: 'slider', start: 0, end: Math.min(100, 800 / points.length) }] : [],
    series: [{ name: card.title, type: 'bar', data: points.map((point) => ({
      value: point.value,
      itemStyle: { color: point.value < 0 ? '#64637b' : '#b3513b' },
    })), markLine: { silent: true, symbol: 'none', data: [{ yAxis: 0 }] } }],
  };
}
