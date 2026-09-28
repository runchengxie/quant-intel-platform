const escapeText = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;',
})[character]);

function wrapText(value, width = 54) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  const lines = [];
  for (let start = 0; start < text.length; start += width) lines.push(text.slice(start, start + width));
  return lines;
}

function sourceDomain(url) {
  try {
    const source = new URL(url);
    return source.protocol === 'https:' ? source.hostname : null;
  } catch {
    return null;
  }
}

function excerpt(markdown, heading, limit = 3) {
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
    if (clean) result.push(clean);
    if (result.length >= limit) break;
  }
  return result;
}

export function buildAsiaReportSvg(report, charts, markdown) {
  if (report?.kind !== 'evening' || !/^\d{4}-\d{2}-\d{2}-evening$/.test(report.id)
    || report.id !== `${report.date}-evening`
    || !Array.isArray(charts) || typeof markdown !== 'string') return null;
  let y = 116;
  const parts = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="__HEIGHT__" viewBox="0 0 960 __HEIGHT__" role="img">',
    `<title>${escapeText(report.date)} 亚洲市场收盘图文复盘</title>`,
    '<desc>包含亚洲市场收盘摘要、六图公开数据、次日观察及关键来源。</desc>',
    '<rect width="960" height="__HEIGHT__" fill="#fff9f2"/>',
    `<text x="54" y="60" fill="#34271f" font-family="sans-serif" font-size="28" font-weight="700">${escapeText(report.date)} 亚洲市场收盘复盘</text>`,
    `<text x="54" y="88" fill="#715f52" font-family="sans-serif" font-size="14">北京时间 19:00 目标版 · 以报告实际生成时间和数据日期为准${report.generation_mode === 'backfill' ? ' · 历史补报' : ''}</text>`,
  ];
  const addText = (value, color = '#34271f', size = 15) => {
    for (const line of wrapText(value)) {
      parts.push(`<text x="54" y="${y}" fill="${color}" font-family="sans-serif" font-size="${size}">${escapeText(line)}</text>`);
      y += 23;
    }
  };
  const addHeading = (heading) => {
    y += 14;
    parts.push(`<text x="54" y="${y}" fill="#34271f" font-family="sans-serif" font-size="20" font-weight="700">${escapeText(heading)}</text>`);
    y += 32;
  };
  addText(report.summary);
  for (const [heading, title, limit] of [
    ['## 一、市场状态', '市场状态', 3], ['### 六维观察', '六维观察', 7],
    ['### 核心矛盾', '核心矛盾', 2], ['### 明日验证', '次日观察', 2],
    ['### 昨日验证复盘', '昨日验证', 2], ['### 二、指数总览', '指数总览', 4],
    ['### 三、市场总览', '市场总览', 3], ['### 四、涨跌停', '涨跌停', 2],
    ['### 五、资金动向', '资金动向', 2], ['### 六、融资融券', '融资融券', 2],
    ['### 七、行业板块 TOP10', '行业板块', 4],
    ['### 八、高成交核心票 TOP10', '高成交个股', 4],
    ['### 九、热门概念 TOP5', '热门概念', 4], ['### 十、极端异动', '极端异动', 3],
    ['### 数据完整度与校准', '数据完整度与校准', 3],
  ]) {
    const lines = excerpt(markdown, heading, limit);
    if (lines.length) {
      addHeading(title);
      for (const line of lines) addText(line);
    }
  }
  addHeading('六图概览');
  const validPoints = [];
  for (const chart of charts) {
    addHeading(`${chart.title} · ${({ ok: '已核实', degraded: '部分缺项', missing: '缺项', skipped: '跳过' })[chart.status] || '缺项'}`);
    if (chart.reason) addText(chart.reason, '#715f52', 13);
    const points = Array.isArray(chart.points) ? chart.points.filter((point) => Number.isFinite(point.value) && sourceDomain(point.source_url)) : [];
    const maxByUnit = new Map();
    for (const point of points) maxByUnit.set(point.unit, Math.max(maxByUnit.get(point.unit) || 0, Math.abs(point.value)));
    for (const point of points) {
      const width = Math.max(2, Math.round(Math.abs(point.value) / (maxByUnit.get(point.unit) || 1) * 260));
      const center = 575;
      const x = point.value < 0 ? center - width : center;
      parts.push(`<text x="54" y="${y}" fill="#34271f" font-family="sans-serif" font-size="14">${escapeText(point.label)}</text>`);
      parts.push(`<rect x="315" y="${y - 14}" width="520" height="15" fill="#efe2d5"/>`);
      parts.push(`<rect x="${x}" y="${y - 12}" width="${width}" height="11" fill="${point.value < 0 ? '#74728b' : '#b3513b'}"/>`);
      parts.push(`<text x="906" y="${y}" text-anchor="end" fill="#34271f" font-family="monospace" font-size="13">${escapeText(Number(point.value).toLocaleString('zh-CN', { maximumFractionDigits: 2 }))} ${escapeText(point.unit)}</text>`);
      y += 21;
      parts.push(`<text x="54" y="${y}" fill="#715f52" font-family="sans-serif" font-size="11">观测日 ${escapeText(point.observation_date)} · ${escapeText(point.source_label)}</text>`);
      y += 27;
      validPoints.push(point);
    }
    if (!points.length) addText('暂无通过审核的公开图表数据。', '#715f52', 13);
  }
  const sources = [...new Set(validPoints.map((point) => `${point.source_label} · ${sourceDomain(point.source_url)}`))];
  if (sources.length) {
    addHeading('关键来源');
    for (const source of sources) addText(source, '#715f52', 12);
    addText('完整来源链接见网页报告。', '#715f52', 12);
  }
  y += 28;
  parts.push(`<line x1="54" y1="${y}" x2="906" y2="${y}" stroke="#d9c7b6"/>`);
  y += 26;
  parts.push(`<text x="54" y="${y}" fill="#715f52" font-family="sans-serif" font-size="12">缺项保持缺项；完整数值、方法与来源见网页报告。市场信息仅供研究参考。</text>`);
  parts.push('</svg>');
  return parts.join('').replaceAll('__HEIGHT__', String(y + 28));
}
