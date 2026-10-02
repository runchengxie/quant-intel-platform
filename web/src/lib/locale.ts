export const SUPPORTED_LOCALES = ['en-US', 'zh-CN'] as const;
export type Locale = typeof SUPPORTED_LOCALES[number];

export const US_REPORT_LABELS = {
  btcSpotGap: ['比特币现货行情', 'Bitcoin spot prices'],
  btcFuturesGap: ['比特币期货行情', 'Bitcoin futures prices'],
  optionalUnavailable: ['可选数据未提供：', 'Optional data unavailable: '],
  researchContext: ['已核实解读', 'Reviewed interpretation'],
  downloadPng: ['下载图片版 PNG', 'Download PNG'],
  pngGenerating: ['正在生成 PNG…', 'Generating PNG…'],
  pngDone: ['图片版 PNG 已生成。', 'PNG generated.'],
  pngFailed: ['PNG 生成失败。请直接阅读网页报告。', 'PNG generation failed. Read the web report instead.'],
  recentReports: ['近期美股报告', 'Recent U.S. reports'],
  generated: ['生成时间', 'Generated'],
  drivers: ['市场驱动因素', 'Market drivers'],
  macroNews: ['经济数据与美联储动态', 'Economic releases and Federal Reserve updates'],
  companyNews: ['公司新闻', 'Company news'],
} as const;

/** Exact source-bound presentation translations, not approval of new research. */
export const US_RESEARCH_TRANSLATIONS = {
  schwabContext20261001: [
    '嘉信理财在10月1日美东09:13发布的盘前观察关注科技股表现与处于多年高位附近的美债收益率。这是当时的市场背景，不是收盘归因，也不证明全天趋势。',
    'Schwab’s October 1 pre-market note, published at 09:13 Eastern Time, focused on technology stocks and Treasury yields near multi-year highs. It describes the morning backdrop and does not establish the cause of the closing move or a full-day trend.',
  ],
  schwabCalendar20261001: [
    '嘉信理财10月1日的日程提示称，下一份美国就业报告将于10月2日美东08:30公布。该信息仅作为后续观察日程，不代表报告已经发布，也不能用于解释10月1日收盘。',
    'Schwab’s October 1 calendar listed the next U.S. employment report for October 2 at 08:30 Eastern Time. This is a scheduled release, not published employment data or an explanation of the October 1 close.',
  ],
  accentureResults20261001: [
    '埃森哲10月1日提交的财报披露，季度收入为186.8亿美元，同比增长6%；下一季度收入指引为177.5亿至184亿美元。公司预计2027财年以当地货币计的收入增长为3%至6%。这些是公司披露和指引，不构成对股价表现的判断。',
    'Accenture’s October 1 earnings filing reported quarterly revenue of USD 18.68 billion, up 6% year over year, and next-quarter revenue guidance of USD 17.75 to 18.4 billion. The company expects fiscal 2027 revenue growth of 3% to 6% in local currency. These figures are company disclosures and guidance, not an assessment of its share-price performance.',
  ],
  mccormickResults20261001: [
    '味好美10月1日发布的第三季度业绩公告披露，销售额增长17.4%，有机销售增长1.9%，调整后每股收益为0.86美元，并维持2026年全年展望。总销售增长与有机增长口径不同，不应混用。',
    'McCormick’s October 1 third-quarter results reported sales growth of 17.4%, organic sales growth of 1.9% and adjusted earnings per share of USD 0.86. The company maintained its full-year 2026 outlook. Total sales growth and organic growth use different measures and should be read separately.',
  ],
} as const;

export function usResearchText(source: string, locale: Locale): string {
  if (locale !== 'en-US') return source;
  return Object.values(US_RESEARCH_TRANSLATIONS).find(([original]) => original === source)?.[1] ?? source;
}

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
