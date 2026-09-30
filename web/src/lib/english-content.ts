const PHRASES: Array<[string, string]> = [
  ['布伦特期货行情', 'Brent futures prices'],
  ['黄金期货行情', 'Gold futures prices'],
  ['白银期货行情', 'Silver futures prices'],
  ['比特币期货行情', 'Bitcoin futures prices'],
  ['部分跨资产行情', 'some cross-asset prices'],
  ['展示已核实的行情图解、市场解读、经济数据和关键来源', 'Shows verified market charts, interpretation, economic data, and key sources'],
  ['亚洲市场收盘复盘', 'Asia market close review'],
  ['亚洲市场收盘复盘（', 'Asia market close review ('],
  ['上证指数', 'SSE Composite'],
  ['深证成指', 'SZSE Component'],
  ['创业板指', 'ChiNext Index'],
  ['指数收盘位置', 'index close position'],
  ['开盘跳空', 'opening gap'],
  ['日内振幅', 'intraday range'],
  ['涨跌分布', 'return distribution'],
  ['最高连板', 'Highest consecutive limit-up streak'],
  ['上涨家数占优', 'advancers outnumbered decliners'],
  ['站上日内均价的个股不足一半', 'fewer than half of stocks were above their intraday VWAP'],
  ['达到一半，才算上涨质量改善', 'reaches half before advance quality improves'],
  ['成交额继续收缩', 'turnover continued to contract'],
  ['指数与行业普遍收涨', 'indexes and sectors broadly gained'],
  ['尚缺：研究解释', 'Missing: research interpretation'],
  ['数据完整度与校准', 'Data completeness and calibration'],
  ['展示已核实的行情图解、市场解读、Economic data和Key sources', 'Shows verified market charts, interpretation, economic data, and key sources'],
  ['美东交易日市场图文复盘', 'U.S. trading day market review'],
  ['亚洲市场Close图文复盘', 'Asia market close review'],
  ['包含亚洲市场Close摘要、市场Breadth、Money flow、Market', 'Includes the Asia close summary, market breadth, money flow, market'],
  ['周度变化及Key sources', 'weekly changes, and key sources'],
  ['目标版 · 以报告实际生成时间和数据日期为准', 'Target edition · based on the actual report generation time and data date'],
  ['热度、脆弱度与六维分数均为Market state观察分，不直接映射仓位，也不构成交易指令。', 'Heat, fragility, and six-dimension scores are market-state observation scores; they do not map directly to position sizing or constitute trading instructions.'],
  ['越高表示该维度越强；Loss risk越高，风险越高。', 'Higher values indicate a stronger dimension; a higher loss-risk score indicates greater risk.'],
  ['收盘上涨家数占优，但站上日内均价的个股不足一半；证据:', 'Advancing stocks outnumbered decliners at the close, but fewer than half of stocks were above their intraday VWAP; evidence:'],
  ['下一观察日站上日内均价的个股达到一半，才算上涨质量改善；条件:', 'Advancing quality improves only when half of stocks are above their intraday VWAP on the next observation day; condition:'],
  ['市场从前一日的Cool脆弱转为Moderately active，指数与行业普遍收涨，但成交额继续收缩，上涨质量仍待确认。', 'The market shifted from the prior day\'s cool and fragile state to moderately active; indexes and sectors broadly gained, but turnover continued to contract and the quality of the advance remains unconfirmed.'],
  ['警告: Profit effect、Loss risk存在missing，observation score按可用指标重加权。', 'Warning: Profit effect and loss risk have missing inputs; observation scores were reweighted using available metrics.'],
  ['完整Source链接见网页报告。', 'Full source links are available in the web report.'],
  ['市场有风险，投资需谨慎。', 'Market risk applies; this is not investment advice.'],
  ['两融数据暂缺（T+1延迟）', 'Margin data unavailable (T+1 delay)'],
  ['生成方式', 'Generation method'],
  ['本报告按计划生成，生成时间为本次实际运行时间。', 'This report was generated on schedule; the generation time is the actual run time.'],
  ['数据日期', 'Data date'],
  ['报告生成时间', 'Report generation time'],
  ['周二 盘后点评', 'Tuesday after-market review'],
  ['最高连板', 'Highest consecutive limit-up streak'],
  ['涨停代表', 'Representative limit-up stocks'],
  ['跌幅靠前行业', 'Worst-performing sectors'],
  ['高成交核心票 TOP10', 'Top 10 high-volume core stocks'],
  ['涨幅前五', 'Top five gainers'],
  ['跌幅前五', 'Top five decliners'],
  ['完整度: 高', 'Completeness: high'],
  ['六维可用', 'Six dimensions available'],
  ['校准: 暂定观察刻度（未回测）。', 'Calibration: provisional observation scale (not backtested).'],
  ['市场状态温和活跃', 'Market state: moderately active'],
  ['市场状态偏冷且脆弱', 'Market state: cool and fragile'],
  ['市场状态偏冷', 'Market state: cool'],
  ['市场信息仅供研究参考。', 'For research reference only.'],
  ['市场信息仅供研究参考', 'For research reference only'],
  ['尚无通过逐点审核的公开图表数据', 'No point-reviewed public chart data is available'],
  ['缺少的数据会标为缺项。完整数值、方法和来源见网页报告。', 'Missing data is labelled explicitly. Full values, methods, and sources are available in the web report.'],
  ['完整数值、方法和来源见网页报告。', 'Full values, methods, and sources are available in the web report.'],
  ['收盘复盘', 'Market close review'],
  ['亚洲市场收盘复盘', 'Asia market close review'],
  ['美股收盘复盘', 'U.S. market close review'],
  ['图解、解读与来源', 'Charts, interpretation, and sources'],
  ['美东交易日', 'U.S. trading day'],
  ['北京时间', 'Beijing time'],
  ['目标日期', 'Target date'],
  ['原报告生成于', 'Source report generated at'],
  ['报告日期', 'Report date'],
  ['市场状态', 'Market state'],
  ['状态', 'Status'],
  ['温和活跃', 'Moderately active'],
  ['偏冷且脆弱', 'Cool and fragile'],
  ['偏冷', 'Cool'],
  ['热度 / 脆弱度', 'Heat / fragility'],
  ['观察分', 'observation score'],
  ['口径', 'Methodology'],
  ['六维观察', 'Six-dimension observation'],
  ['观察分越高表示该维度越强；亏钱风险越高，风险越高。', 'A higher score indicates a stronger dimension; a higher loss-risk score indicates greater risk.'],
  ['流动性', 'Liquidity'],
  ['广度', 'Breadth'],
  ['赚钱效应', 'Profit effect'],
  ['亏钱风险', 'Loss risk'],
  ['趋势确认', 'Trend confirmation'],
  ['轮动质量', 'Rotation quality'],
  ['核心矛盾', 'Core tension'],
  ['次日观察', 'Next-session watch'],
  ['明日验证', 'Next-day validation'],
  ['指数总览', 'Index overview'],
  ['市场总览', 'Market overview'],
  ['涨跌停', 'Price limits'],
  ['资金动向', 'Money flow'],
  ['融资融券', 'Margin financing'],
  ['行业板块', 'Industry sectors'],
  ['高成交个股', 'High-volume stocks'],
  ['热门概念', 'Hot concepts'],
  ['极端异动', 'Extreme movers'],
  ['数据完整度与校准', 'Data completeness and calibration'],
  ['数据状态', 'Data status'],
  ['当日公开复盘。', 'Public same-day review.'],
  ['尚缺：研究解释', 'Missing: research interpretation'],
  ['关键来源', 'Key sources'],
  ['亚洲市场图表', 'Asian market charts'],
  ['综合盘面', 'Market breadth dashboard'],
  ['资金流向', 'Money flow'],
  ['热点概念', 'Hot concepts'],
  ['市场温度', 'Market temperature'],
  ['周度概览', 'Weekly overview'],
  ['四大指数收盘涨跌', 'Four major index returns'],
  ['美股个股日涨跌', 'U.S. stock daily returns'],
  ['美债收益率水平', 'U.S. Treasury yield levels'],
  ['美债收益率当日变动', 'U.S. Treasury daily yield changes'],
  ['跨资产日涨跌', 'Cross-asset daily returns'],
  ['经济数据', 'Economic data'],
  ['标普 500', 'S&P 500'],
  ['道指', 'Dow Jones'],
  ['纳指', 'Nasdaq'],
  ['罗素 2000', 'Russell 2000'],
  ['2 年期美债收益率水平', '2-year Treasury yield'],
  ['5 年期美债收益率水平', '5-year Treasury yield'],
  ['10 年期美债收益率水平', '10-year Treasury yield'],
  ['30 年期美债收益率水平', '30-year Treasury yield'],
  ['布伦特', 'Brent'],
  ['黄金', 'Gold'],
  ['白银', 'Silver'],
  ['BTC/USD 现货', 'BTC/USD spot'],
  ['观测日', 'Observed'],
  ['收盘', 'Close'],
  ['美元/桶', 'USD/barrel'],
  ['美元/金衡盎司', 'USD/troy oz'],
  ['美元/BTC', 'USD/BTC'],
  ['美元', 'USD'],
  ['美国财政部', 'U.S. Treasury'],
  ['数据: Tushare / market-data-platform', 'Data: Tushare / market-data-platform'],
  ['主题: 研究编辑部', 'Desk: Research editorial'],
  ['生成:', 'Generated:'],
  ['同比', 'YoY'],
  ['失业率', 'Unemployment rate'],
  ['非农就业月变动', 'Nonfarm payroll change'],
  ['千人', ' thousand'],
  ['尚缺：', 'Missing: '],
  ['金银或比特币行情', 'gold, silver, or Bitcoin prices'],
  ['完整Source链接', 'Full source links'],
  ['数据暂缺', 'Data unavailable'],
  ['缺项', 'missing'],
  ['上涨', 'Up'],
  ['下跌', 'Down'],
  ['平盘', 'Flat'],
  ['上涨率', 'up rate'],
  ['跌幅', 'decline'],
  ['涨幅', 'return'],
  ['涨停率', 'limit-up rate'],
  ['跌停率', 'limit-down rate'],
  ['成交额', 'turnover'],
  ['成交', 'volume'],
  ['万亿', 'trillion'],
  ['亿', ' hundred million'],
  ['板', ' boards'],
  ['站上VWAP占比', 'above-VWAP share'],
  ['站上日内均价', 'above intraday VWAP'],
  ['个股', 'stocks'],
  ['指数', 'indexes'],
  ['行业', 'sectors'],
  ['概念', 'concept'],
  ['龙头', 'leader'],
  ['代码', 'Ticker'],
  ['中位数', 'median'],
  ['均涨跌', 'average return'],
  ['总成交', 'total turnover'],
  ['家', ' stocks'],
  ['行业 / 均涨跌 / 中位数 / 家数 / 上涨率', 'Industry / average return / median / count / up rate'],
  ['概念 / 涨幅 / 龙头 / 涨停数', 'Concept / return / leader / limit-up count'],
  ['来源', 'Source'],
];

const PHRASE_PATTERN = new RegExp(PHRASES.map(([source]) => source.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'g');

/** Translate public presentation text without altering facts, dates, URLs, or source identifiers. */
export function toEnglishPresentation(value: string): string {
  const exact = value
    .replace(/热度、脆弱度与六维分数均为市场状态观察分，不直接映射仓位，也不构成交易指令/g, 'Heat, fragility, and six-dimension scores are market-state observation scores; they do not map directly to position sizing or constitute trading instructions')
    .replace(/观察分越高表示该维度越强；亏钱风险越高，风险越高/g, 'Higher scores indicate stronger dimensions; a higher loss-risk score indicates greater risk')
    .replace(/警告[:：]\s*赚钱效应、亏钱风险存在缺项，观察分按可用指标重加权/g, 'Warning: profit effect and loss risk have missing inputs; observation scores were reweighted using available metrics')
    .replace(/市场从前一日的偏冷脆弱转为温和活跃，指数与行业普遍收涨，但成交额继续收缩，上涨质量仍待确认/g, 'The market shifted from the prior day\'s cool and fragile state to moderately active; indexes and sectors broadly gained, but turnover continued to contract and advance quality remains unconfirmed')
    .replace(/亚洲市场收盘图文复盘/g, 'Asia market close review')
    .replace(/包含亚洲市场收盘摘要、市场广度、资金流向、市场温度、周度变化及关键来源/g, 'Includes the Asia close summary, market breadth, money flow, market temperature, weekly changes, and key sources')
    .replace(/北京时间 19:00 目标版 · 以报告实际生成时间和数据日期为准/g, '19:00 Beijing time target edition · based on the actual report generation time and data date')
    .replace(/近几日涨跌分布/g, 'Recent return distribution')
    .replace(/涨跌分布/g, 'Return distribution')
    .replace(/成交额走势（亿）/g, 'Turnover trend (100m)')
    .replace(/成交额/g, 'turnover')
    .replace(/市场广度/g, 'market breadth')
    .replace(/关键来源/g, 'key sources')
    .replace(/市场温度/g, 'market temperature')
    .replace(/周度变化/g, 'weekly changes');
  return exact.replace(PHRASE_PATTERN, (match) => PHRASES.find(([source]) => source === match)?.[1] || match)
    // A few source records omit spaces or vary punctuation. Keep this second pass
    // deliberately limited to report labels and explanatory prose; proper nouns
    // such as Chinese company and concept names remain source-faithful.
    .replace(/(\d+)年期美债/g, '$1-year Treasury')
    .replace(/热度、脆弱度与六维分数均为市场状态观察分，不直接映射仓位，也不构成交易指令/g, 'Heat, fragility, and six-dimension scores are market-state observation scores; they do not map directly to position sizing or constitute trading instructions')
    .replace(/观察分越高表示该维度越强；亏钱风险越高，风险越高/g, 'Higher scores indicate stronger dimensions; a higher loss-risk score indicates greater risk')
    .replace(/警告[:：]\s*赚钱效应、亏钱风险存在缺项，观察分按可用指标重加权/g, 'Warning: profit effect and loss risk have missing inputs; observation scores were reweighted using available metrics')
    .replace(/市场从前一日的偏冷脆弱转为温和活跃，指数与行业普遍收涨，但成交额继续收缩，上涨质量仍待确认/g, 'The market shifted from the prior day\'s cool and fragile state to moderately active; indexes and sectors broadly gained, but turnover continued to contract and advance quality remains unconfirmed')
    .replace(/上涨率/g, 'up rate')
    .replace(/站上VWAP占比/g, 'above-VWAP share')
    .replace(/站上日内均价/g, 'above intraday VWAP')
    .replace(/成交额加权涨跌/g, 'turnover-weighted return')
    .replace(/成交额加权与中位数偏离/g, 'turnover-weighted return minus median')
    .replace(/高成交标的/g, 'high-volume names')
    .replace(/净流入/g, 'net inflow')
    .replace(/净流出/g, 'net outflow')
    .replace(/领涨集中度/g, 'leader concentration')
    .replace(/收盘上涨家数占优/g, 'advancers outnumbered decliners at the close')
    .replace(/上涨质量/g, 'advance quality')
    .replace(/下一观察日/g, 'next observation day')
    .replace(/条件/g, 'condition')
    .replace(/维度/g, 'dimension')
    .replace(/证据/g, 'evidence')
    .replace(/状态/g, 'status')
    .replace(/较弱/g, 'weak')
    .replace(/偏强/g, 'strong')
    .replace(/中性/g, 'neutral')
    .replace(/低风险/g, 'low risk')
    .replace(/较强/g, 'strong')
    .replace(/收益率/g, 'yield')
    .replace(/当日变动/g, 'daily change')
    .replace(/日涨跌/g, 'daily return')
    .replace(/收盘涨跌/g, 'close return')
    .replace(/涨跌停/g, 'price limits')
    .replace(/涨停数/g, 'limit-up count')
    .replace(/上涨行业占比/g, 'share of advancing sectors')
    .replace(/行业中位涨跌/g, 'sector median return')
    .replace(/指数中位涨跌/g, 'index median return')
    .replace(/中位数涨跌/g, 'median return')
    .replace(/涨幅超5%占比/g, 'share gaining over 5%')
    .replace(/跌幅超5%占比/g, 'share falling over 5%')
    .replace(/涨停率/g, 'limit-up rate')
    .replace(/跌停率/g, 'limit-down rate')
    .replace(/风险/g, 'risk')
    .replace(/历史中位/g, 'historical median')
    .replace(/分位/g, 'percentile')
    .replace(/占比/g, 'share')
    .replace(/净流入/g, 'net inflow')
    .replace(/净流出/g, 'net outflow')
    .replace(/加权涨跌/g, 'weighted return')
    .replace(/偏离/g, 'difference')
    .replace(/涨跌/g, 'return')
    .replace(/上涨/g, 'advancing')
    .replace(/下跌/g, 'declining')
    .replace(/平盘/g, 'flat')
    .replace(/家数/g, 'count')
    .replace(/资金动向/g, 'Money flow')
    .replace(/大单资金代理/g, 'Large-order money-flow proxy')
    .replace(/融资融券/g, 'Margin financing')
    .replace(/行业板块/g, 'Industry sectors')
    .replace(/高成交个股/g, 'High-volume stocks')
    .replace(/涨跌/g, 'return')
    .replace(/图表/g, 'charts')
    .replace(/图解/g, 'charts')
    .replace(/行情charts/g, 'market charts')
    .replace(/Economic data/g, 'economic data')
    .replace(/年期美债/g, '-year Treasury')
    .replace(/科创50/g, 'STAR Market 50')
    .replace(/全市场/g, 'all-market')
    .replace(/中位数/g, 'median')
    .replace(/中位/g, 'median')
    .replace(/超5%/g, 'over 5%')
    .replace(/涨停/g, 'limit-up')
    .replace(/跌停/g, 'limit-down')
    .replace(/大单/g, 'large-order')
    .replace(/标的/g, 'names')
    .replace(/一、/g, 'I. ')
    .replace(/昨日验证复盘/g, 'Prior-day validation review')
    .replace(/站上 VWAP 比例/g, 'Above-VWAP share')
    .replace(/位置/g, 'position')
    .replace(/指标/g, 'metric')
    .replace(/数 \/ Up率/g, 'count / up rate')
    .replace(/数/g, 'count')
    .replace(/率/g, 'rate')
    .replace(/综合仪表盘/g, 'Market breadth dashboard')
    .replace(/市场从前一日的Cool脆弱/g, 'The market shifted from the prior day\'s cool and fragile')
    .replace(/质量仍待确认/g, 'advance quality remains unconfirmed')
    .replace(/构volume易指令/g, 'constitute trading instructions')
    .replace(/不直接映射仓位/g, 'do not map directly to position sizing')
    .replace(/市场状态/g, 'market state')
    .replace(/展示已核实的/g, 'Shows verified ')
    .replace(/经济数据和关键来源/g, 'economic data and key sources')
    .replace(/加权与mediandifference/g, 'weighted return minus median')
    .replace(/高volumenames相对strong/g, 'high-volume names were relatively strong')
    .replace(/生成时间/g, 'Generation time')
    .replace(/报告Generation method/g, 'Report generation method')
    .replace(/房地产/g, 'Real estate')
    .replace(/传媒/g, 'Media')
    .replace(/计算机/g, 'Computers')
    .replace(/电力设备/g, 'Power equipment')
    .replace(/通信/g, 'Telecom')
    .replace(/有色金属/g, 'Nonferrous metals')
    .replace(/环保/g, 'Environmental services')
    .replace(/电子/g, 'Electronics')
    .replace(/钢铁/g, 'Steel')
    .replace(/石油石化/g, 'Oil and petrochemicals')
    .replace(/缺项/g, 'missing')
    .replace(/经济数据/g, 'economic data')
    .replace(/关键来源/g, 'key sources')
    .replace(/完整Source链接见网页报告/g, 'Full source links are available in the web report')
    .replace(/报告Generation method/g, 'Report generation method')
    .replace(/周度变化/g, 'weekly changes')
    .replace(/市场Breadth/g, 'market breadth')
    .replace(/Money flow/g, 'money flow')
    .replace(/Market temperature/g, 'market temperature')
    .replace(/行情图解/g, 'market charts')
    .replace(/市场解读/g, 'market interpretation')
    .replace(/数据日期/g, 'Data date')
    .replace(/报告生成时间/g, 'Report generation time')
    .replace(/二、/g, 'II. ')
    .replace(/三、/g, 'III. ')
    .replace(/四、/g, 'IV. ')
    .replace(/五、/g, 'V. ')
    .replace(/六、/g, 'VI. ')
    .replace(/七、/g, 'VII. ')
    .replace(/八、/g, 'VIII. ')
    .replace(/九、/g, 'IX. ')
    .replace(/十、/g, 'X. ')
    .replace(/Target date\s+(\d{4}-\d{2}-\d{2})；Source report generated at\s+([^。]+)（Beijing time）。/g, 'Target date $1; source report generated at $2 (Beijing time).')
    .replace(/（([^）]+)）/g, ' ($1)')
    .replace(/；/g, '; ')
    .replace(/。/g, '. ')
    .replace(/：/g, ': ');
}
