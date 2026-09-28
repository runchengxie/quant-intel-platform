const { test } = require('node:test');
const assert = require('node:assert/strict');
const { mkdtempSync, mkdirSync, writeFileSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const path = require('node:path');

test('US daily history loads five dated public markdown reports in date order', async () => {
  const root = mkdtempSync(path.join(tmpdir(), 'us-daily-history-'));
  const previous = process.env.ASTRO_DATA_ROOT;
  try {
    mkdirSync(path.join(root, 'data'));
    mkdirSync(path.join(root, 'reports'));
    const days = ['2026-09-24', '2026-09-23'];
    writeFileSync(path.join(root, 'data/market_daily_reports.json'), JSON.stringify({
      schema_version: 'market_intel_pages.us_daily_history.v1',
      reports: days.map((day) => ({ run_id: `daily-${day}`, publication: 'public' })),
    }));
    for (const day of days) writeFileSync(path.join(root, `reports/${day}-market-daily.md`), `# ${day}\n`);
    process.env.ASTRO_DATA_ROOT = root;
    const { loadMarketDailyHistory } = await import('../src/lib/reports.mjs');

    assert.deepEqual(loadMarketDailyHistory().map((row) => [row.date, row.markdown]), [
      ['2026-09-24', '# 2026-09-24\n'],
      ['2026-09-23', '# 2026-09-23\n'],
    ]);
  } finally {
    if (previous === undefined) delete process.env.ASTRO_DATA_ROOT;
    else process.env.ASTRO_DATA_ROOT = previous;
    rmSync(root, { recursive: true });
  }
});
