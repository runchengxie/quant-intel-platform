import { sectionLines } from './asia-report-tables.ts';
import { ASIA_IMAGE_LABELS as labels } from './locale.ts';

interface Draw {
  parts: string[];
  y: number;
  present: (value: string) => string;
  node: (x: number, y: number, value: string, options?: { color?: string; size?: number; anchor?: string }) => string;
  text: (value: string, color?: string, size?: number) => void;
}
type Metric = [string, string, number];
const UP = '#b54839';
const DOWN = '#248072';
const FLAT = '#777777';
const patternNumber = '([+-]?\\d+(?:\\.\\d+)?)';

function card(draw: Draw, key: string, label: string, value: string): void {
  draw.parts.push(`<g data-card="${key}"><rect x="54" y="${draw.y}" width="852" height="58" fill="#f5ebe1"/>`);
  draw.parts.push(draw.node(66, draw.y + 22, draw.present(label), { size: 13 }));
  draw.parts.push(draw.node(894, draw.y + 38, value, { size: 20, anchor: 'end' }));
  draw.parts.push('</g>');
  draw.y += 76;
}

function counts(draw: Draw, rows: Metric[]): void {
  const total = rows.reduce((sum, row) => sum + row[2], 0);
  if (!total) return;
  let left = 54;
  for (const [index, [key, , value]] of rows.entries()) {
    const width = 852 * value / total;
    draw.parts.push(`<rect data-count="${key}" data-value="${value}" x="${left}" y="${draw.y}" width="${width}" height="18" fill="${[UP, DOWN, FLAT][index]}"/>`);
    left += width;
  }
  draw.y += 42;
  for (const [index, [, label, value]] of rows.entries()) {
    draw.parts.push(draw.node(54 + index * 284, draw.y, `${draw.present(label)}: ${value.toLocaleString('en-US')}${draw.present(labels.countUnit[0])}`, { size: 12 }));
  }
  draw.y += 30;
}

function returns(draw: Draw, rows: Metric[]): void {
  const scale = Math.max(...rows.map(row => Math.abs(row[2])), 0.01);
  for (const [key, label, value] of rows) {
    const width = 240 * Math.abs(value) / scale;
    draw.parts.push(draw.node(54, draw.y, draw.present(label), { size: 13 }));
    draw.parts.push(`<line x1="590" y1="${draw.y - 14}" x2="590" y2="${draw.y + 3}" stroke="${FLAT}"/>`);
    draw.parts.push(`<rect data-metric="${key}" data-value="${value}" x="${value < 0 ? 590 - width : 590}" y="${draw.y - 11}" width="${width}" height="13" fill="${value < 0 ? DOWN : UP}"/>`);
    draw.parts.push(draw.node(906, draw.y, `${value > 0 ? '+' : ''}${value.toFixed(2)}%`, { size: 13, anchor: 'end' }));
    draw.y += 30;
  }
}

function matches(lines: string[], pattern: RegExp): RegExpExecArray | null {
  for (const line of lines) {
    const match = pattern.exec(line.replace(/\[(?:OK|WARN)\]\s*/g, ''));
    if (match && match.slice(1).every(value => value === undefined || ['万亿', '亿', '万'].includes(value) || (Number.isFinite(Number(value)) && Math.abs(Number(value)) <= Number.MAX_SAFE_INTEGER))) return match;
  }
  return null;
}

function moneyText(draw: Draw, amount: string, unit: string): string {
  const units: Record<string, string> = { '万亿': labels.trillionUnit[0], '亿': labels.cny100m[0], '万': labels.tenThousandUnit[0], '': labels.yuanUnit[0] };
  return `${amount}${draw.present(units[unit])}`;
}

function validBreadth(row: RegExpExecArray): boolean {
  const [up, down, flat, rate] = row.slice(1).map(Number);
  const total = up + down + flat;
  return rate <= 100 && (total === 0 ? rate === 0 : Math.abs(up / total * 100 - rate) <= 0.051);
}

/** Graphics supplement the original published text; never read private source assets. */
export function renderReportPanel(draw: Draw, markdown: string, heading: string): void {
  const lines = sectionLines(markdown, heading);
  if (heading === '### 三、市场总览') {
    const change = matches(lines, new RegExp(`^全市场中位数涨跌\\s*${patternNumber}% \\| 成交额加权涨跌 ${patternNumber}% \\| 总成交 ${patternNumber}(万亿|亿|万)?$`));
    const breadth = matches(lines, /^上涨 (\d+) 家 \| 下跌 (\d+) 家 \| 平盘 (\d+) 家 \| 上涨率 (\d+(?:\.\d+)?)%$/);
    if (!change || !breadth || Number(change[3]) < 0 || Number(change[1]) < -100 || Number(change[2]) < -100 || !validBreadth(breadth)) return;
    draw.parts.push('<g data-report-panel="overview">');
    card(draw, 'turnover', labels.totalTurnover[0], moneyText(draw, change[3], change[4] || ''));
    returns(draw, [['median', labels.medianReturn[0], Number(change[1])], ['weighted', labels.weightedReturn[0], Number(change[2])]]);
    counts(draw, [['up', labels.upCount[0], Number(breadth[1])], ['down', labels.downCount[0], Number(breadth[2])], ['flat', labels.flatCount[0], Number(breadth[3])]]);
    draw.text(labels.weightedNote[0], FLAT, 12);
  } else if (heading === '### 四、涨跌停') {
    const limits = matches(lines, /^涨停 (\d+) 家 \| 跌停 (\d+) 家 \| 涨幅>5% (\d+) 家 \| 跌幅>5% (\d+) 家$/);
    if (!limits) return;
    draw.parts.push('<g data-report-panel="limits">');
    const board = matches(lines.map(line => line.replace(/^>\s*/, '')), /^最高连板:\s*(\d+) 板$/);
    if (board) card(draw, 'max-board', labels.maxBoard[0], `${board[1]}${draw.present(labels.boardUnit[0])}`);
    counts(draw, [['limit-up', labels.limitUp[0], Number(limits[1])], ['limit-down', labels.limitDown[0], Number(limits[2])]]);
    counts(draw, [['over-five', labels.overFive[0], Number(limits[3])], ['below-five', labels.belowFive[0], Number(limits[4])]]);
    draw.text(labels.overlapNote[0], FLAT, 12);
  } else if (heading === '### 五、资金动向') {
    const flow = matches(lines, new RegExp(`^大单资金代理\\s*${patternNumber}(万亿|亿|万)? \\| 净流入 (\\d+) 家 / 净流出 (\\d+) 家$`));
    if (!flow) return;
    draw.parts.push('<g data-report-panel="flow">');
    draw.text(`${draw.present(labels.flowProxy[0])}: ${moneyText(draw, Number(flow[1]).toFixed(2), flow[2] || '')}`);
    counts(draw, [['inflow', labels.inflowCount[0], Number(flow[3])], ['outflow', labels.outflowCount[0], Number(flow[4])]]);
    draw.text(labels.proxyNote[0], FLAT, 12);
  } else return;
  draw.parts.push('</g>');
}
