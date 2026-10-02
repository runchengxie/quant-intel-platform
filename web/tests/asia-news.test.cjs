const test = require('node:test');
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { mkdtempSync, mkdirSync, writeFileSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const path = require('node:path');

const markdown = '# reviewed report';
const reportHash = createHash('sha256').update(markdown).digest('hex');

async function payload() {
  const { publicReportIdentity } = await import('../src/lib/report-image-identity.ts');
  const claim = '收入增长 6%。', claimEn = 'Revenue rose 6%.';
  const value = { schema_version: 'market_intel.asia_news_public.v1', publication: 'public', report_id: '2026-09-30-evening', date: '2026-09-30', kind: 'evening', generated_at: '2026-09-30T20:30:00+08:00', cutoff: '2026-09-30T19:00:00+08:00', report_sha256: reportHash, status: 'reviewed', markets: { cn: [{ evidence_id: 'asia.' + 'a'.repeat(64), market: 'cn', source_url: 'https://www.sse.com.cn/x', publisher: 'SSE', published_at: '2026-09-30T14:00:00+08:00', time_precision: 'timestamp', event_date: null, source_sha256: 'a'.repeat(64), claim, claim_sha256: publicReportIdentity(claim), claim_en: claimEn, claim_en_sha256: publicReportIdentity(claimEn), applicability: 'eligible' }], hk: [] } };
  return { ...value, content_sha256: publicReportIdentity(value) };
}

test('public news binds exact content and canonical report', async () => {
  const { validateAsiaNews, newsPresentation } = await import('../src/lib/asia-news.ts');
  const value = validateAsiaNews(await payload(), '2026-09-30-evening', markdown);
  assert.equal(newsPresentation(value.markets.cn[0], 'en-US').claim, 'Revenue rose 6%.');
  assert.equal(newsPresentation(value.markets.cn[0], 'zh-CN').claim, '收入增长 6%。');
  assert.throws(() => validateAsiaNews(value, value.report_id, 'changed report'));
  value.markets.cn[0].claim_en = 'Revenue rose 7%.';
  assert.throws(() => validateAsiaNews(value, value.report_id, markdown));
});

test('missing translation preserves evidence with an explicit source-language label', async () => {
  const { newsPresentation } = await import('../src/lib/asia-news.ts');
  const item = (await payload()).markets.cn[0];
  item.claim_en = null;
  const view = newsPresentation(item, 'en-US');
  assert.equal(view.claim, '收入增长 6%。');
  assert.match(view.translationNote, /translation unavailable/i);
  assert.equal(view.href, 'https://www.sse.com.cn/x');
  assert.match(view.sourceTime, /2026|Sep/);
});

test('public readers reject private extensions and refetched duplicate documents', async () => {
  const { validateAsiaNews } = await import('../src/lib/asia-news.ts');
  const { publicReportIdentity } = await import('../src/lib/report-image-identity.ts');
  for (const place of ['envelope', 'item', 'duplicate']) {
    const value = await payload();
    if (place === 'envelope') value.private_receipt = { reviewer: 'private' };
    if (place === 'item') value.markets.cn[0].raw_body = 'private';
    if (place === 'duplicate') value.markets.cn.push({ ...value.markets.cn[0], evidence_id: 'asia.' + 'b'.repeat(64) });
    const { content_sha256, ...body } = value;
    value.content_sha256 = publicReportIdentity(body);
    assert.throws(() => validateAsiaNews(value, value.report_id, markdown));
  }
});

test('optional loader is offline, rejects traversal, and reads only matching report content', async () => {
  const { loadAsiaNews } = await import('../src/lib/asia-news.ts');
  const root = mkdtempSync(path.join(tmpdir(), 'asia-news-'));
  const previous = process.env.ASTRO_DATA_ROOT;
  try {
    process.env.ASTRO_DATA_ROOT = root;
    assert.equal(loadAsiaNews('2026-09-30-evening'), null);
    assert.throws(() => loadAsiaNews('../secret'));
    mkdirSync(path.join(root, 'data/asia_news'), { recursive: true });
    mkdirSync(path.join(root, 'reports'));
    writeFileSync(path.join(root, 'reports/2026-09-30-evening.md'), markdown);
    writeFileSync(path.join(root, 'data/asia_news/2026-09-30-evening.json'), JSON.stringify(await payload()));
    assert.equal(loadAsiaNews('2026-09-30-evening').markets.cn.length, 1);
    writeFileSync(path.join(root, 'reports/2026-09-30-evening.md'), 'changed');
    assert.throws(() => loadAsiaNews('2026-09-30-evening'));
  } finally {
    if (previous === undefined) delete process.env.ASTRO_DATA_ROOT; else process.env.ASTRO_DATA_ROOT = previous;
    rmSync(root, { recursive: true, force: true });
  }
});
