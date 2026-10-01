import { ASIA_IMAGE_LABELS as labels } from './locale.ts';

export interface ReportTable {
  key: string;
  headers: string[];
  rows: string[][];
  fallback: string[];
  notes: string[];
  preview: number;
}

/** Only consume the existing published Markdown facts, never chart-source assets. */
export function sectionLines(markdown: string, heading: string): string[] {
  const lines = markdown.split('\n');
  const start = lines.findIndex((line) => line.trim() === heading);
  if (start < 0) return [];
  const end = lines.findIndex((line, index) => index > start && /^#{1,3} /.test(line));
  return lines.slice(start + 1, end < 0 ? undefined : end).map((line) => line.trim())
    .filter((line) => line && line !== '---' && !/^\*数据:/.test(line));
}

const cells = (line: string): string[] => line.split(/(?<!\\)\|/).slice(1, -1)
  .map((cell) => cell.trim().replace(/\\\|/g, '|'));

const missingOr = (value: string, valid: (value: string) => boolean): boolean => value === 'N/A' || valid(value);
const decimal = (value: string): boolean => /^\d+(?:\.\d+)?$/.test(value) && Number.isFinite(Number(value));
const count = (value: string): boolean => /^\d+$/.test(value) && Number.isFinite(Number(value));
// Published zero returns may omit a sign; nonzero returns retain an explicit sign.
const signedPercent = (value: string): boolean => /^(?:[+-]\d+(?:\.\d+)?|0(?:\.0+)?)%$/.test(value)
  && Number.isFinite(Number(value.slice(0, -1)));
const share = (value: string): boolean => /^\d+(?:\.\d+)?%$/.test(value)
  && Number(value.slice(0, -1)) <= 100;
const leader = (value: string): boolean => {
  const match = /^(.+)\(([^()]+)\)$/.exec(value);
  return Boolean(match && match[1].trim() && signedPercent(match[2]));
};

function validFields(key: string, row: string[]): boolean {
  if (key === 'industry') return Boolean(row[0]) && missingOr(row[1], signedPercent)
    && missingOr(row[2], signedPercent) && missingOr(row[3], count) && missingOr(row[4], share);
  if (key === 'turnover') return /^\d{6}$/.test(row[0]) && missingOr(row[1], decimal) && missingOr(row[2], signedPercent);
  return Boolean(row[0]) && missingOr(row[1], signedPercent) && missingOr(row[2], leader) && missingOr(row[3], count);
}

export function reportTable(markdown: string, heading: string): ReportTable | null {
  const lines = sectionLines(markdown, heading);
  if (!lines.length) return null;
  const table: ReportTable = { key: '', headers: [], rows: [], fallback: [], notes: [], preview: 5 };
  if (heading === '### 二、指数总览') {
    table.key = 'indices';
    table.headers = [labels.index[0], labels.close[0], labels.return[0], labels.amount[0]];
    table.preview = Infinity;
    for (const line of lines) {
      const match = /^(.+?):\s*(\d+(?:\.\d+)?|N\/A)\s*(?:\[(?:OK|WARN)\]\s*)?([+-]?\d+(?:\.\d+)?%|N\/A)\s*\|\s*成交\s*(\d+(?:\.\d+)?亿|N\/A)$/.exec(line);
      if (match) table.rows.push([match[1], match[2], match[3], match[4].replace(/亿$/, '')]);
      else table.fallback.push(line);
    }
  } else if (heading === '### 十、极端异动') {
    table.key = 'movers';
    table.headers = [labels.moversGroup[0], labels.ticker[0], labels.return[0]];
    table.preview = 10;
    for (const line of lines) {
      const match = /^(涨幅前五|跌幅前五):\s*(.+)$/.exec(line);
      if (!match) { table.fallback.push(line); continue; }
      for (const entry of match[2].split('、')) {
        const row = /^([\d]{6}\.(?:SZ|SH|BJ))\(([+-]?\d+(?:\.\d+)?%)\)$/.exec(entry.trim());
        if (row) table.rows.push([match[1], row[1], row[2]]);
        else table.fallback.push(entry);
      }
    }
  } else {
    const specs: Record<string, [string, string[]]> = {
      '### 七、行业板块 TOP10': ['industry', ['行业', '均涨跌', '中位数', '家数', '上涨率']],
      '### 八、高成交核心票 TOP10': ['turnover', ['代码', '成交额(亿)', '涨跌']],
      '### 九、热门概念 TOP5': ['concepts', ['概念', '涨幅', '龙头', '涨停数']],
    };
    const spec = specs[heading];
    if (!spec) return null;
    table.key = spec[0];
    let headerFound = false;
    for (const line of lines) {
      if (/^\|[\s|:-]+\|$/.test(line)) continue;
      if (!line.startsWith('|')) { table.notes.push(line); continue; }
      if (!line.endsWith('|')) { table.fallback.push(line); continue; }
      const row = cells(line);
      if (!headerFound && row.join('|') === spec[1].join('|')) {
        table.headers = row.map((cell) => cell === '成交额(亿)' ? labels.amount[0] : cell);
        headerFound = true;
      } else if (headerFound && row.length === table.headers.length && validFields(table.key, row)) table.rows.push(row);
      else table.fallback.push(line);
    }
  }
  return table;
}

export function dailyReturn(value: string): number | null {
  if (!/^[+-]?\d+(?:\.\d+)?%$/.test(value)) return null;
  const result = Number(value.slice(0, -1));
  return Number.isFinite(result) ? result : null;
}
