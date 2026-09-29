type TrendFact = { id?: unknown; value?: unknown; observation_date?: unknown };
type TrendReport = { date?: unknown; publication?: unknown; facts?: unknown };
export type MarketTrendPoint = { date: string; value: number };

export function buildMarketTrend(reports: TrendReport[], factId: string): MarketTrendPoint[] {
  const byDate = new Map<string, MarketTrendPoint>();
  for (const report of reports) {
    const date = report?.date;
    if (report?.publication !== 'public' || typeof date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(date)) continue;
    const facts = Array.isArray(report.facts) ? report.facts as TrendFact[] : [];
    const fact = facts.find((row) => row.id === factId);
    const value = fact?.value;
    if (fact?.observation_date !== date || typeof value !== 'number' || !Number.isFinite(value)) continue;
    byDate.set(date, { date, value });
  }
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date)).slice(-5);
}
