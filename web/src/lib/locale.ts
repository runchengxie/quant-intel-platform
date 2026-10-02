export const SUPPORTED_LOCALES = ['en-US', 'zh-CN'] as const;
export type Locale = typeof SUPPORTED_LOCALES[number];

export const US_REPORT_LABELS = {
  btcSpotGap: ['比特币现货行情', 'Bitcoin spot prices'],
  btcFuturesGap: ['比特币期货行情', 'Bitcoin futures prices'],
  optionalUnavailable: ['可选数据未提供：', 'Optional data unavailable: '],
} as const;

/** Stable semantic keys; each label has an English and Chinese presentation. */
export const ASIA_IMAGE_LABELS = {
  title: ['亚洲市场收盘复盘', 'Asia market close review'],
  description: ['包含亚洲市场收盘摘要、市场广度、资金流向、市场温度、周度变化及关键来源。', 'Includes the Asia close summary, market breadth, money flow, market temperature, weekly changes, and key sources.'],
  index: ['指数', 'Index'],
  close: ['收盘点位', 'Close level'],
  amount: ['成交额（亿）', 'Turnover (CNY 100m)'],
  return: ['日涨跌', 'Daily return'],
  indexReturns: ['指数日涨跌', 'Index daily returns'],
  originalFacts: ['原报告事实 · 指数成交额存在重叠，不加总。', 'Original report facts · Index turnover overlaps and is not summed.'],
  fallback: ['无法解析的原始行', 'Unparsed row'],
  preview: ['预览 {shown} / {total} 行；其余见完整报告。', 'Preview {shown} / {total} rows; see the full report for the rest.'],
  missingReturn: ['日涨跌缺项；不绘制柱形。', 'Daily return missing; no bar drawn.'],
  direction: ['正值上涨 · 负值下跌 · 方向不表示数据审核状态。', 'Positive: up · Negative: down · Direction does not indicate data review status.'],
  ticker: ['代码', 'Ticker'],
  moversGroup: ['分组', 'Group'],
  gainers: ['涨幅前五', 'Top gainers'],
  decliners: ['跌幅前五', 'Top decliners'],
  data: ['数据:', 'Data:'],
  unavailable: ['暂无可公开数据', 'No public data available'],
  unreviewed: ['暂无通过审核的公开数据。', 'No reviewed public data available.'],
  skipped: ['跳过', 'Skipped'],
  missingFooter: ['缺少的数据会标为缺项。完整数值、方法和来源见网页报告。市场信息仅供研究参考。', 'Missing data is labelled explicitly. Full values, methods and sources are in the web report. For research reference only.'],
  edition: ['北京时间 19:00 目标版 · 以报告实际生成时间和数据日期为准', '19:00 Beijing time edition · Actual generation time and data dates apply'],
  backfill: ['历史补报', 'Historical backfill'],
} as const;

export function asiaImageLabel(key: keyof typeof ASIA_IMAGE_LABELS, locale: Locale): string {
  return ASIA_IMAGE_LABELS[key][locale === 'en-US' ? 1 : 0];
}

export const LOCALE_PATHS: Record<Locale, string> = {
  'en-US': '/en/',
  'zh-CN': '/?locale=zh-CN',
};

export function localePath(locale: Locale, base = ''): string {
  return `${base}${LOCALE_PATHS[locale]}`;
}
