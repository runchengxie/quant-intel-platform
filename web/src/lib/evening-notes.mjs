const EVENING_ONLY_START = '2026-09-25';

function sectionText(report, title) {
  const section = (report.sections || []).find((item) => item.title?.includes(title));
  return (section?.paragraphs || []).filter((item) => typeof item === 'string').join('\n');
}

function noteFromReport(report) {
  const state = sectionText(report, '市场状态').match(/(?:^|\n)-?\s*状态[:：]\s*([^。；\n]{1,20})/);
  const breadth = sectionText(report, '市场总览').match(/上涨率\s*(\d+(?:\.\d+)?)%/);
  const percent = breadth ? Number(breadth[1]) : null;
  const parts = [];
  if (state) parts.push(`市场状态${state[1].trim()}`);
  if (percent !== null && Number.isFinite(percent) && percent >= 0 && percent <= 100) {
    parts.push(`上涨率 ${breadth[1]}%`);
  }
  if (!parts.length) return null;
  return {
    date: report.date,
    reportId: report.id,
    text: `${parts.join('；')}。`,
    source: 'evening',
  };
}

export function buildEveningNotes(reports) {
  return reports
    .filter((row) => row?.kind === 'evening' && row.date >= EVENING_ONLY_START)
    .map(noteFromReport)
    .filter(Boolean)
    .sort((a, b) => b.date.localeCompare(a.date))
    .slice(0, 5);
}
