const EVENING_ONLY_START = '2026-09-25';

type ReportSection = { title?: unknown; paragraphs?: unknown };
type Report = { date?: unknown; id?: unknown; kind?: unknown; sections?: unknown };
export type EveningNote = { date: string; reportId: string; text: string; source: 'evening' };

function sectionText(report: Report, title: string): string {
  const sections = Array.isArray(report.sections) ? report.sections as ReportSection[] : [];
  const section = sections.find((item) => typeof item.title === 'string' && item.title.includes(title));
  return (Array.isArray(section?.paragraphs) ? section.paragraphs : [])
    .filter((item): item is string => typeof item === 'string').join('\n');
}

function noteFromReport(report: Report): EveningNote | null {
  if (typeof report.date !== 'string' || typeof report.id !== 'string') return null;
  const state = sectionText(report, '市场状态').match(/(?:^|\n)-?\s*状态[:：]\s*([^。；\n]{1,20})/);
  const breadth = sectionText(report, '市场总览').match(/上涨率\s*(\d+(?:\.\d+)?)%/);
  const percent = breadth ? Number(breadth[1]) : null;
  const parts = [];
  if (state) parts.push(`市场状态${state[1].trim()}`);
  if (percent !== null && Number.isFinite(percent) && percent >= 0 && percent <= 100) {
    parts.push(`上涨率 ${breadth?.[1]}%`);
  }
  if (!parts.length) return null;
  return {
    date: report.date,
    reportId: report.id,
    text: `${parts.join('；')}。`,
    source: 'evening',
  };
}

export function buildEveningNotes(reports: Report[]): EveningNote[] {
  return reports
    .filter((row) => row.kind === 'evening' && typeof row.date === 'string' && row.date >= EVENING_ONLY_START)
    .map(noteFromReport)
    .filter(Boolean)
    .filter((row): row is EveningNote => row !== null)
    .sort((a, b) => b.date.localeCompare(a.date))
    .slice(0, 5);
}
