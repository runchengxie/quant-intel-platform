import type { ChartCard, ChartPoint } from './chart-data.ts';
import { dailyReturn, reportTable, type ReportTable } from './asia-report-tables.ts';
import { ASIA_IMAGE_LABELS as labels, asiaImageLabel, type Locale } from './locale.ts';
import { toEnglishPresentation } from './english-content.ts';
import { renderReportPanel } from './asia-report-panels.ts';

interface EveningReport {
  kind: 'evening';
  id: string;
  date: string;
  summary: string;
  generation_mode?: string;
}

interface DimensionRow { label: string; score: number | null; status?: string; evidence?: string; }

interface SvgDraw { parts: string[]; y: number; present: (value: string) => string; node: typeof textNode; text: (value: string, color?: string, size?: number) => void; }

const escapeText = (value: unknown): string => String(value ?? '').replace(/[&<>"']/g, (character) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;',
} as Record<string, string>)[character] ?? '');

// Approximate rendered advance: CJK takes a full em, Latin a little over half.
// Translate whole cells before wrapping to avoid fragmented English phrases.
function cellLines(value: string, pixels: number, size = 13): string[] {
  const lines: string[] = [];
  let line = '';
  let used = 0;
  const advanceOf = (char: string) => /[\u2e80-\uffef]/u.test(char) ? size : size * 0.58;
  for (const char of value) {
    const advance = advanceOf(char);
    if (line && used + advance > pixels) {
      const boundary = line.lastIndexOf(' ');
      if (boundary > 0 && /[A-Za-z]/.test(char)) {
        lines.push(line.slice(0, boundary).trimEnd());
        line = line.slice(boundary + 1);
        used = [...line].reduce((sum, letter) => sum + advanceOf(letter), 0);
      } else { lines.push(line.trimEnd()); line = ''; used = 0; }
    }
    if (!line && char === ' ') continue;
    line += char;
    used += advance;
  }
  if (line) lines.push(line);
  return lines.length ? lines : ['—'];
}

function alignedTable(draw: SvgDraw, table: ReportTable): void {
  const widths: Record<string, number[]> = {
    indices: [280, 180, 170, 222], industry: [280, 145, 145, 130, 152],
    turnover: [280, 300, 272], concepts: [220, 120, 350, 162], movers: [280, 300, 272],
  };
  const columns = widths[table.key];
  draw.parts.push(`<g data-table="${table.key}">`);
  const row = (values: string[], header = false) => {
    const lines = values.map((value, i) => cellLines(draw.present(value), columns[i] - 24));
    const height = Math.max(...lines.map((cell) => cell.length)) * 18 + 14;
    if (header) draw.parts.push(`<rect x="54" y="${draw.y - 15}" width="852" height="${height}" fill="${TRACK}"/>`);
    let x = 54;
    for (const [i, cell] of lines.entries()) {
      const numeric = !header && /^(?:[+-]?\d|N\/A)/.test(values[i]) && !(table.key === 'turnover' && i === 0) && !(table.key === 'movers' && i === 1);
      const color = !header && /^[+-]\d.*%$/.test(values[i]) ? (values[i].startsWith('-') ? DOWN : UP) : INK;
      for (const [j, line] of cell.entries()) draw.parts.push(textNode(numeric ? x + columns[i] - 12 : x + 12, draw.y + j * 18, line,
        { size: 13, anchor: numeric ? 'end' : 'start', weight: header ? '600' : '400', color }));
      x += columns[i];
    }
    draw.y += height;
    draw.parts.push(`<line x1="54" y1="${draw.y - 16}" x2="906" y2="${draw.y - 16}" stroke="${REPORT_LINE}"/>`);
  };
  if (table.headers.length) row(table.headers, true);
  for (const values of table.rows.slice(0, table.preview)) row(values);
  draw.parts.push('</g>');
  if (table.rows.length > table.preview) draw.text(draw.present(labels.preview[0]).replace('{shown}', String(table.preview)).replace('{total}', String(table.rows.length)), MUTED, 12);
  for (const line of table.fallback) draw.text(`${draw.present(labels.fallback[0])}: ${line}`, MUTED, 12);
  for (const note of table.notes.slice(0, 2)) draw.text(note, MUTED, 12);
  if (table.key !== 'indices') return;
  draw.text(labels.indexReturns[0], INK, 15);
  const values = table.rows.map((item) => dailyReturn(item[2])).filter((value): value is number => value !== null);
  const scale = Math.max(...values.map(Math.abs), 0.01);
  for (const item of table.rows) {
    const value = dailyReturn(item[2]);
    draw.parts.push(textNode(54, draw.y, draw.present(item[0]), { size: 13 }));
    if (value === null) {
      draw.parts.push(textNode(350, draw.y, draw.present(labels.missingReturn[0]), { size: 12, color: MUTED }));
    } else {
      const width = 300 * Math.abs(value) / scale;
      draw.parts.push(`<line x1="540" y1="${draw.y - 15}" x2="540" y2="${draw.y + 3}" stroke="${MUTED}"/>`);
      draw.parts.push(`<rect data-index-return="${escapeText(item[0])}" data-value="${value}" x="${value < 0 ? 540 - width : 540}" y="${draw.y - 12}" width="${width}" height="14" fill="${value < 0 ? DOWN : value > 0 ? UP : FLAT}"/>`);
      draw.parts.push(draw.node(906, draw.y, item[2], { size: 13, anchor: 'end' }));
    }
    draw.y += 28;
  }
  draw.text(labels.direction[0], MUTED, 12);
  draw.text(labels.originalFacts[0], MUTED, 12);
}

function sourceDomain(url: string): string | null {
  try {
    const source = new URL(url);
    return source.protocol === 'https:' ? source.hostname : null;
  } catch {
    return null;
  }
}

function excerpt(markdown: string, heading: string, limit = 3): string[] {
  const lines = markdown.split('\n');
  const start = lines.findIndex((line) => line.trim() === heading);
  if (start < 0) return [];
  const result = [];
  for (const line of lines.slice(start + 1)) {
    if (/^#{2,3} /.test(line)) break;
    if (/^\|[\s|:-]+\|$/.test(line.trim())) continue;
    const clean = line.trim().startsWith('|')
      ? line.split('|').map((cell) => cell.trim()).filter(Boolean).join(' / ')
      : line.replace(/^[-*>\s]+/, '').trim();
    if (clean && !/^N\/A$/i.test(clean)) result.push(clean);
    if (result.length >= limit) break;
  }
  return result;
}

function sixDimensionRows(markdown: string): DimensionRow[] | null {
  const labels = ['流动性', '广度', '赚钱效应', '亏钱风险', '趋势确认', '轮动质量'];
  const lines = markdown.split('\n');
  const start = lines.findIndex((line) => line.trim() === '### 六维观察');
  if (start < 0) return null;
  const found = new Map();
  for (const line of lines.slice(start + 1)) {
    if (/^#{2,3} /.test(line)) break;
    if (!line.trim().startsWith('|')) continue;
    const cells = line.split(/(?<!\\)\|/).slice(1, -1).map((cell) => cell.trim().replace(/\\\|/g, '|'));
    if (cells.length !== 4 || !labels.includes(cells[0])) continue;
    const score = Number(cells[1]);
    found.set(cells[0], {
      score: /^(?:0|[1-9]\d?|100)(?:\.\d+)?$/.test(cells[1]) && Number.isFinite(score) && score <= 100 ? score : null,
      status: cells[2], evidence: cells[3],
    });
  }
  return labels.map((label) => ({ label, ...found.get(label) }));
}

function sixDimensionBars(draw: SvgDraw, rows: DimensionRow[]): void {
  draw.text('观察分越高表示该维度越强；亏钱风险越高，风险越高。', MUTED, 12);
  for (const row of rows) {
    if (row.score === null || row.score === undefined) {
      draw.text(`${row.label} · 缺项`, MUTED, 13);
      if (row.status && row.status !== '缺项') draw.text(row.status, MUTED, 12);
      if (row.evidence) draw.text(row.evidence, MUTED, 12);
      draw.y += 9;
      continue;
    }
    const color = row.label === '亏钱风险' ? UP : DOWN;
    draw.parts.push(draw.node(54, draw.y, row.label, { size: 14, weight: '600' }));
    draw.parts.push(`<rect x="245" y="${draw.y - 12}" width="520" height="14" fill="${TRACK}"/>`);
    draw.parts.push(`<rect data-dimension="${escapeText(row.label)}" x="245" y="${draw.y - 12}" width="${520 * row.score / 100}" height="14" fill="${color}"/>`);
    draw.parts.push(draw.node(906, draw.y, `${formatNumber(row.score, 1)} / 100 · ${row.status}`, { size: 13, color, anchor: 'end' }));
    draw.y += 20;
    if (row.evidence) draw.text(row.evidence, MUTED, 12);
    draw.y += 9;
  }
}

const REPORT_BG = 'var(--report-bg, #fff9f2)';
const INK = 'var(--report-ink, #34271f)';
const MUTED = 'var(--report-muted, #715f52)';
const REPORT_LINE = 'var(--report-line, #d9c7b6)';
const UP = '#b64d33';
const DOWN = '#5c7182';
const TRACK = '#efe2d5';
const FLAT = '#b9a99a';
const CHART_KEYS = ['dashboard', 'moneyflow', 'topic', 'sentiment', 'weekly_chart'];
const FONT = "'Source Han Sans CN', 'Noto Sans CJK SC', 'Noto Sans SC', 'PingFang SC', sans-serif";

const formatNumber = (value: number, digits = 1): string => Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits });
interface TextOptions { size?: number; color?: string; anchor?: string; weight?: string; }
const textNode = (x: number, y: number, value: unknown, { size = 13, color = INK, anchor = 'start', weight = '400' }: TextOptions = {}) =>
  `<text x="${x}" y="${y}" text-anchor="${anchor}" fill="${color}" font-family="sans-serif" font-size="${size}" font-weight="${weight}">${escapeText(value)}</text>`;
const usablePoints = (chart: ChartCard): ChartPoint[] => ['ok', 'degraded'].includes(chart.status)
  ? chart.points.filter((point) => Number.isFinite(point.value) && Boolean(sourceDomain(point.source_url))) : [];

function sourceNote(draw: SvgDraw, points: ChartPoint[]): void {
  const dates = [...new Set(points.map((point) => point.observation_date))].sort();
  const sources = [...new Set(points.map((point) => point.source_label))];
  draw.text(`观测日：${dates.length > 1 ? `${dates[0]} 至 ${dates.at(-1)}` : dates[0]} · 来源：${sources.join('、')}`, MUTED, 12);
}

function breadth(draw: SvgDraw, points: ChartPoint[], title = '市场广度'): boolean {
  const rows = ['上涨家数', '下跌家数', '平盘家数'].map((label) => points.find((point) => point.label === label));
  if (rows.some((row) => !row)) return false;
  const presentRows = rows as [ChartPoint, ChartPoint, ChartPoint];
  if (new Set(presentRows.map((row) => row.observation_date)).size !== 1) return false;
  const total = presentRows.reduce((sum, row) => sum + row.value, 0);
  if (total <= 0) return false;
  draw.parts.push(draw.node(54, draw.y, title, { size: 15, weight: '600' }));
  draw.y += 16;
  let left = 54;
  for (const [index, row] of presentRows.entries()) {
    const width = 852 * row.value / total;
    draw.parts.push(`<rect x="${left}" y="${draw.y}" width="${width}" height="25" fill="${[UP, DOWN, FLAT][index]}"/>`);
    left += width;
  }
  draw.y += 45;
  draw.parts.push(draw.node(54, draw.y, `涨 ${formatNumber(presentRows[0].value, 0)} 家`, { color: UP }));
  draw.parts.push(draw.node(350, draw.y, `跌 ${formatNumber(presentRows[1].value, 0)} 家`, { color: DOWN }));
  draw.parts.push(draw.node(650, draw.y, `平 ${formatNumber(presentRows[2].value, 0)} 家`, { color: MUTED }));
  draw.y += 29;
  return true;
}

function metricCards(draw: SvgDraw, points: ChartPoint[], labels: string[]): void {
  const rows = labels.map((label) => points.find((point) => point.label === label)).filter((point): point is ChartPoint => Boolean(point));
  if (!rows.length) return;
  const width = 852 / rows.length;
  for (const [index, point] of rows.entries()) {
    const x = 54 + index * width;
    draw.parts.push(`<rect x="${x}" y="${draw.y}" width="${width - 10}" height="60" fill="#f5ebe1"/>`);
    draw.parts.push(draw.node(x + 12, draw.y + 21, point.label, { size: 12, color: MUTED }));
    draw.parts.push(draw.node(x + 12, draw.y + 46, `${formatNumber(point.value, 2)} ${point.unit}`, { size: 18, weight: '600', color: point.value < 0 ? DOWN : UP }));
  }
  draw.y += 78;
}

function trend(draw: SvgDraw, points: ChartPoint[], prefix: string, title: string, unit: string): boolean {
  const rows = points.filter((point) => point.label.startsWith(`${prefix} `) && point.unit === unit)
    .sort((a, b) => a.observation_date.localeCompare(b.observation_date)).slice(-5);
  if (rows.length < 2) return false;
  draw.parts.push(draw.node(54, draw.y, title, { size: 15, weight: '600' }));
  draw.y += 20;
  const top = draw.y;
  const values = rows.map((row) => row.value);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = Math.max(high - low, 1);
  const vertices = rows.map((row, index) => ({
    x: 100 + index * 750 / Math.max(rows.length - 1, 1),
    y: top + 62 - (row.value - low) / span * 45,
  }));
  draw.parts.push(`<line x1="54" y1="${top + 64}" x2="906" y2="${top + 64}" stroke="${TRACK}"/>`);
  draw.parts.push(`<polyline points="${vertices.map(({ x, y }) => `${x},${y}`).join(' ')}" fill="none" stroke="${UP}" stroke-width="3"/>`);
  for (const [index, row] of rows.entries()) {
    const { x, y } = vertices[index];
    draw.parts.push(`<circle cx="${x}" cy="${y}" r="4" fill="${UP}"/>`);
    draw.parts.push(draw.node(x, top + 80, row.observation_date.slice(5), { size: 11, color: MUTED, anchor: 'middle' }));
    draw.parts.push(draw.node(x, top + 98, formatNumber(row.value, 0), { size: 11, anchor: 'middle' }));
  }
  draw.y = top + 124;
  return true;
}

function rankedBars(draw: SvgDraw, rows: ChartPoint[], title: string, color: string, width = 400, x = 54): void {
  if (!rows.length) return;
  draw.parts.push(draw.node(x, draw.y, title, { size: 15, weight: '600' }));
  draw.y += 22;
  const max = Math.max(...rows.map((point) => Math.abs(point.value)), 1);
  for (const point of rows) {
    draw.parts.push(draw.node(x, draw.y, point.label, { size: 12 }));
    draw.parts.push(draw.node(x + width, draw.y, `${formatNumber(point.value, 2)} ${point.unit}`, { size: 12, color, anchor: 'end' }));
    draw.parts.push(`<rect x="${x}" y="${draw.y + 7}" width="${width}" height="8" fill="${TRACK}"/>`);
    draw.parts.push(`<rect x="${x}" y="${draw.y + 7}" width="${Math.max(2, width * Math.abs(point.value) / max)}" height="8" fill="${color}"/>`);
    draw.y += 38;
  }
  draw.y += 9;
}

function fallbackRows(draw: SvgDraw, points: ChartPoint[]): void {
  if (!points.length) return;
  draw.parts.push(draw.node(54, draw.y, '已核实数据', { size: 15, weight: '600' }));
  draw.y += 22;
  const max = Math.max(...points.map((point) => Math.abs(point.value)), 1);
  for (const point of points) {
    const color = point.value < 0 ? DOWN : UP;
    draw.parts.push(draw.node(54, draw.y, point.label, { size: 12 }));
    draw.parts.push(draw.node(906, draw.y, `${formatNumber(point.value, 2)} ${point.unit}`, { size: 12, color, anchor: 'end' }));
    draw.parts.push(`<rect x="54" y="${draw.y + 7}" width="852" height="8" fill="${TRACK}"/>`);
    draw.parts.push(`<rect x="54" y="${draw.y + 7}" width="${Math.max(2, 852 * Math.abs(point.value) / max)}" height="8" fill="${color}"/>`);
    draw.y += 38;
  }
  draw.y += 9;
}

function weekly(draw: SvgDraw, points: ChartPoint[]): void {
  const byDate = new Map();
  for (const point of points) {
    const match = /^(上涨家数|下跌家数|平盘家数|成交额) (\d{4}-\d{2}-\d{2})$/.exec(point.label);
    if (match) {
      if (!byDate.has(match[2])) byDate.set(match[2], {});
      byDate.get(match[2])[match[1]] = point;
    }
  }
  const dates = [...byDate.keys()].sort().slice(-5);
  const breadthRows = dates.filter((date) => ['上涨家数', '下跌家数', '平盘家数'].every((key) => byDate.get(date)[key]));
  if (breadthRows.length) {
    draw.parts.push(draw.node(54, draw.y, '近几日涨跌分布', { size: 15, weight: '600' }));
    draw.y += 22;
    for (const date of breadthRows) {
      const row = byDate.get(date);
      const values = ['上涨家数', '下跌家数', '平盘家数'].map((key) => row[key].value);
      const total = values.reduce((sum, value) => sum + value, 0);
      if (total <= 0) continue;
      draw.parts.push(draw.node(54, draw.y + 15, date.slice(5), { size: 12 }));
      let x = 145;
      for (const [index, value] of values.entries()) {
        const width = 650 * value / total;
        draw.parts.push(`<rect x="${x}" y="${draw.y}" width="${width}" height="22" fill="${[UP, DOWN, FLAT][index]}"/>`);
        x += width;
      }
      draw.parts.push(draw.node(906, draw.y + 15, `${formatNumber(values[0] / total * 100, 0)}% 涨`, { size: 12, anchor: 'end', color: UP }));
      draw.y += 32;
    }
    draw.y += 12;
  }
  trend(draw, points, '成交额', '成交额走势（亿）', '亿');
}

export function buildAsiaReportSvg(report: EveningReport, charts: ChartCard[], markdown: string, present: (value: string) => string = (value) => value, locale?: Locale): string | null {
  if (report?.kind !== 'evening' || !/^\d{4}-\d{2}-\d{2}-evening$/.test(report.id)
    || report.id !== `${report.date}-evening`
    || !Array.isArray(charts) || typeof markdown !== 'string') return null;
  // Preserve legacy English callers that supply only the fourth presenter argument.
  const selectedLocale = locale ?? (present('亚洲市场收盘复盘') === 'Asia market close review' ? 'en-US' : 'zh-CN');
  const catalog = new Map<string, string>(Object.entries(labels).map(([key, values]) =>
    [values[0], asiaImageLabel(key as keyof typeof labels, selectedLocale)]));
  const presentText = (value: string) => catalog.get(value) ?? present(selectedLocale === 'en-US' ? toEnglishPresentation(value) : value);
  let y = 116;
  const parts = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="__HEIGHT__" viewBox="0 0 960 __HEIGHT__" role="img">',
    `<title>${escapeText(report.date)} ${escapeText(asiaImageLabel('title', selectedLocale))}</title>`,
    `<desc>${escapeText(asiaImageLabel('description', selectedLocale))}</desc>`,
    `<rect width="960" height="__HEIGHT__" fill="${REPORT_BG}"/>`,
    `<text x="54" y="60" fill="${INK}" font-family="sans-serif" font-size="28" font-weight="700">${escapeText(report.date)} ${escapeText(asiaImageLabel('title', selectedLocale))}</text>`,
    `<text x="54" y="88" fill="${MUTED}" font-family="sans-serif" font-size="14">${escapeText(asiaImageLabel('edition', selectedLocale))}${report.generation_mode === 'backfill' ? ` · ${escapeText(asiaImageLabel('backfill', selectedLocale))}` : ''}</text>`,
  ];
  const addText = (value: string, color = INK, size = 15) => {
    for (const line of cellLines(presentText(value.replace(/\[(?:OK|WARN)\]\s*/g, '')), 852, size)) {
      parts.push(`<text x="54" y="${y}" fill="${color}" font-family="sans-serif" font-size="${size}">${escapeText(line)}</text>`);
      y += 23;
    }
  };
  const addHeading = (heading: string) => {
    y += 14;
    parts.push(`<text x="54" y="${y}" fill="${INK}" font-family="sans-serif" font-size="20" font-weight="700">${escapeText(presentText(heading))}</text>`);
    y += 32;
  };
  const draw: SvgDraw = {
    parts,
    present: presentText,
    node: (x, position, value, options) => textNode(x, position, presentText(String(value ?? '')), options),
    get y() { return y; },
    set y(value) { y = value; },
    text: addText,
  };
  addText(report.summary);
  for (const [heading, title, limit] of ([
    ['## 一、市场状态', '市场状态', 3], ['### 六维观察', '六维观察', 7],
    ['### 核心矛盾', '核心矛盾', 2], ['### 明日验证', '次日观察', 2],
    ['### 昨日验证复盘', '昨日验证', 2], ['### 二、指数总览', '指数总览', 4],
    ['### 三、市场总览', '市场总览', Infinity], ['### 四、涨跌停', '涨跌停', Infinity],
    ['### 五、资金动向', '资金动向', Infinity], ['### 六、融资融券', '融资融券', 2],
    ['### 七、行业板块 TOP10', '行业板块', 4],
    ['### 八、高成交核心票 TOP10', '高成交个股', 4],
    ['### 九、热门概念 TOP5', '热门概念', 4], ['### 十、极端异动', '极端异动', 3],
    ['### 数据完整度与校准', '数据完整度与校准', 3],
  ] as Array<[string, string, number]>)) {
    const table = reportTable(markdown, heading);
    if (table) {
      addHeading(title);
      alignedTable(draw, table);
      continue;
    }
    if (heading === '### 六维观察') {
      const rows = sixDimensionRows(markdown);
      if (rows) {
        addHeading(title);
        sixDimensionBars(draw, rows);
      }
      continue;
    }
    const lines = excerpt(markdown, heading, limit as number);
    if (lines.length) {
      addHeading(title);
      for (const line of lines) addText(line);
      renderReportPanel(draw, markdown, heading);
    }
  }
  const provenance = markdown.split('\n').filter((line) => /^\*数据:/.test(line.trim()));
  for (const line of provenance) addText(line.replace(/^\*|\*$/g, ''), MUTED, 12);
  addHeading('亚洲市场图表');
  const validPoints: ChartPoint[] = [];
  const chartTitles: Record<string, string> = { dashboard: '综合盘面', moneyflow: '资金流向', topic: '热点概念', sentiment: '市场温度', weekly_chart: '周度概览' };
  const statusTitles: Record<string, string> = { ok: '已核实', degraded: '部分缺项', missing: '缺项', skipped: '跳过' };
  for (const key of CHART_KEYS) {
    const chart: ChartCard = charts.find((item) => item.key === key) || {
      key, title: chartTitles[key], status: 'missing', points: [], reason: '暂无可公开数据',
    };
    addHeading(`${chartTitles[key]} · ${statusTitles[chart.status] || '缺项'}`);
    if (chart.reason) addText(chart.reason, MUTED, 13);
    const points = usablePoints(chart);
    if (!points.length) {
      if (!chart.reason) addText('暂无通过审核的公开数据。', MUTED, 13);
      continue;
    }
    const chartStart = draw.y;
    if (key === 'dashboard') {
      breadth(draw, points);
      metricCards(draw, points, ['平均涨跌', '涨停家数', '最高连板']);
      trend(draw, points, '融资余额', '融资余额走势（亿）', '亿');
    } else if (key === 'moneyflow') {
      const start = draw.y;
      rankedBars(draw, points.filter((point) => point.value > 0), '主力净流入', UP, 400);
      const leftEnd = draw.y;
      draw.y = start;
      rankedBars(draw, points.filter((point) => point.value < 0), '主力净流出', DOWN, 400, 506);
      draw.y = Math.max(draw.y, leftEnd);
    } else if (key === 'topic') {
      rankedBars(draw, points.slice(0, 10), '热点权重', UP, 690);
    } else if (key === 'sentiment') {
      breadth(draw, points);
      metricCards(draw, points, ['平均涨跌', '涨停家数', '个股总数']);
    } else if (key === 'weekly_chart') {
      weekly(draw, points);
    }
    if (draw.y === chartStart) fallbackRows(draw, points);
    sourceNote(draw, points);
    validPoints.push(...points);
  }
  const sources = [...new Set(validPoints.map((point) => `${point.source_label} · ${sourceDomain(point.source_url)}`))];
  if (sources.length) {
    addHeading('关键来源');
    for (const source of sources) addText(source, MUTED, 12);
    addText('完整来源链接见网页报告。', MUTED, 12);
  }
  y += 28;
    parts.push(`<line x1="54" y1="${y}" x2="906" y2="${y}" stroke="${REPORT_LINE}"/>`);
  y += 26;
  parts.push(draw.node(54, y, labels.missingFooter[0], { color: MUTED, size: 12 }));
  parts.push('</svg>');
  return parts.join('').replaceAll('__HEIGHT__', String(y + 28))
    .replaceAll('font-family="sans-serif"', `font-family="${FONT}"`);
}
