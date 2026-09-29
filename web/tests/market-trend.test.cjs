const test = require('node:test');
const assert = require('node:assert/strict');

test('five-day trend uses only public same-day observed facts', async () => {
  const { buildMarketTrend } = await import('../src/lib/market-trend.ts');
  const row = (date, value, observationDate = date, publication = 'public') => ({
    date, publication, facts: [{ id: 'index.spx.change_percent', value, observation_date: observationDate }],
  });
  const result = buildMarketTrend([
    row('2026-09-18', 1), row('2026-09-19', 2), row('2026-09-20', 3),
    row('2026-09-21', 4), row('2026-09-22', 5), row('2026-09-23', -0.8),
    row('2026-09-24', 99, '2026-09-23'), row('2026-09-25', 3, undefined, 'private'),
  ], 'index.spx.change_percent');
  assert.deepEqual(result.map((item) => item.date), [
    '2026-09-19', '2026-09-20', '2026-09-21', '2026-09-22', '2026-09-23',
  ]);
  assert.equal(result.at(-1).value, -0.8);
});

test('five-day trend rejects non-finite and mismatched facts', async () => {
  const { buildMarketTrend } = await import('../src/lib/market-trend.ts');
  assert.deepEqual(buildMarketTrend([
    { date: '2026-09-25', publication: 'public', facts: [{
      id: 'index.spx.change_percent', value: 'bad', observation_date: '2026-09-25',
    }] },
    { date: '2026-09-24', publication: 'public', facts: [{
      id: 'index.spx.change_percent', value: null, observation_date: '2026-09-24',
    }] },
  ], 'index.spx.change_percent'), []);
});
