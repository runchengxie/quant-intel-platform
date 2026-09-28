const test = require('node:test');
const assert = require('node:assert/strict');

test('chart loader requests only the selected report identity', async () => {
  const { loadChart } = await import('../src/lib/chart-data.ts');
  const urls = [];
  const payload = {
    schema_version: 'market_intel.a_share_charts.v1',
    publication: 'public',
    report_id: '2026-09-18-morning',
    date: '2026-09-18',
    kind: 'morning',
    generated_at: '2026-09-18T08:00:00+08:00',
    content_sha256: 'a'.repeat(64),
    charts: [],
  };
  await loadChart('2026-09-18-morning', async (url) => {
    urls.push(url);
    return { ok: true, json: async () => payload };
  });
  assert.deepEqual(urls, ['/quant-intel-platform/data/charts/2026-09-18-morning.json']);
  await assert.rejects(() => loadChart('../private', async () => ({})), /identity/);
  await assert.rejects(() => loadChart('2026-09-18-evening', async () => ({
    ok: true, json: async () => payload,
  })), /identity/);
});

test('chart loader rejects a chart with an untyped point', async () => {
  const { loadChart } = await import('../src/lib/chart-data.ts');
  await assert.rejects(() => loadChart('2026-09-18-evening', async () => ({
    ok: true,
    json: async () => ({
      publication: 'public',
      report_id: '2026-09-18-evening',
      charts: [{ title: '涨跌', points: [{ label: '甲', value: '1.2' }] }],
    }),
  })), /identity/);
});

test('chart loader rejects a payload without the public chart contract', async () => {
  const { loadChart } = await import('../src/lib/chart-data.ts');
  await assert.rejects(() => loadChart('2026-09-18-evening', async () => ({
    ok: true,
    json: async () => ({ publication: 'public', report_id: '2026-09-18-evening', charts: [] }),
  })), /identity/);
});

test('chart option has units, signed values, a zero line and tooltip source date', async () => {
  const { toOption } = await import('../src/lib/chart-data.ts');
  const option = toOption({ title: '涨跌', points: [
    { label: '甲', value: 1.2, unit: '%', observation_date: '2026-09-18', source_label: '甲源' },
    { label: '乙', value: -2, unit: '%', observation_date: '2026-09-18', source_label: '乙源' },
  ] });
  assert.deepEqual(option.series[0].data.map((row) => row.value), [1.2, -2]);
  assert.equal(option.series[0].markLine.data[0].yAxis, 0);
  assert.match(option.tooltip.formatter({ dataIndex: 0 }), /\+1\.2 %.*2026-09-18/s);
  assert.match(option.tooltip.formatter({ dataIndex: 1 }), /−2 %/);
});
