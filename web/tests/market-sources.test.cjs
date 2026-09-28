const test = require('node:test');
const assert = require('node:assert/strict');

test('paired facts with one source render one link, while distinct sources remain visible', async () => {
  const { uniqueFactSources } = await import('../src/lib/market-sources.mjs');
  const treasury = 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates';
  const fred = 'https://fred.stlouisfed.org/series/DGS2';
  assert.deepEqual(uniqueFactSources([{ source_url: treasury }, { source_url: treasury }]), [
    { href: treasury, label: '美国财政部' },
  ]);
  assert.deepEqual(uniqueFactSources([{ source_url: treasury }, { source_url: fred }]), [
    { href: treasury, label: '美国财政部' }, { href: fred, label: 'FRED' },
  ]);
});

test('crypto source links retain provider names', async () => {
  const { uniqueFactSources } = await import('../src/lib/market-sources.mjs');
  assert.deepEqual(uniqueFactSources([
    { source_url: 'https://www.coingecko.com/en/coins/bitcoin' },
    { source_url: 'https://www.kraken.com/prices/bitcoin' },
  ]).map((item) => item.label), ['CoinGecko', 'Kraken']);
});

test('reviewed historical index source names the publisher', async () => {
  const { uniqueFactSources } = await import('../src/lib/market-sources.mjs');
  assert.equal(uniqueFactSources([{
    id: 'index.spx.change_percent',
    source_url: 'https://www-cdn.abcnews.com/Business/wireStory/example',
  }])[0].label, 'ABC News');
});
