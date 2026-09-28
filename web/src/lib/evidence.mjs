const TABLE_COLUMNS = {
  '六维观察': ['维度', '观察分', '状态', '证据'],
  '七、行业板块 TOP10': ['行业', '均涨跌', '中位数', '家数', '上涨率'],
  '八、高成交核心票 TOP10': ['代码', '成交额', '涨跌'],
};

export function formatEvidenceLine(section, text) {
  const columns = TABLE_COLUMNS[section];
  if (!columns || !/^\|.*\|$/.test(text.trim())) return text;
  const cells = text.trim().slice(1, -1).split('|').map((cell) => cell.trim());
  if (cells.length !== columns.length || cells.every((cell) => /^:?-+:?$/.test(cell))) return text;
  return cells.map((cell, index) => `${columns[index]}：${cell}`).join('；');
}
