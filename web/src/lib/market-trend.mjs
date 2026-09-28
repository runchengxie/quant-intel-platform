export function buildMarketTrend(reports, factId) {
  const byDate = new Map();
  for (const report of reports) {
    const date = report?.date;
    if (report?.publication !== 'public' || !/^\d{4}-\d{2}-\d{2}$/.test(date || '')) continue;
    const fact = report.facts?.find((row) => row.id === factId);
    const value = fact?.value;
    if (fact?.observation_date !== date || typeof value !== 'number' || !Number.isFinite(value)) continue;
    byDate.set(date, { date, value });
  }
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date)).slice(-5);
}
