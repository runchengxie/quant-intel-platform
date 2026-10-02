import { createHash } from 'node:crypto';
import { existsSync, readFileSync, realpathSync } from 'node:fs';
import path from 'node:path';
import { dataRoot } from './reports.ts';
import { publicReportIdentity } from './report-image-identity.ts';
import { ASIA_NEWS_LABELS, type Locale } from './locale.ts';

export interface AsiaNewsItem {
  evidence_id: string; market: 'cn' | 'hk'; source_url: string; publisher: string;
  published_at: string; time_precision: 'date' | 'timestamp'; event_date: string | null;
  source_sha256: string; claim: string; claim_sha256: string;
  claim_en: string | null; claim_en_sha256: string | null;
  applicability: 'eligible' | 'holiday_context';
}
export interface AsiaNewsPublicArtifact {
  schema_version: string; publication: string; report_id: string; date: string; kind: string;
  generated_at: string; cutoff: string; report_sha256: string; content_sha256: string;
  status: 'reviewed' | 'missing'; markets: { cn: AsiaNewsItem[]; hk: AsiaNewsItem[] };
}
const hash = /^[a-f0-9]{64}$/;
const text = (v: unknown): v is string => typeof v === 'string' && !!v.trim() && v.length <= 2000
  && !/\/home\/|\/Users\/|\b(?:sk-|ghp_|github_pat_)[\w-]{8,}|\bBearer\s+\S+|(?:api_key|password|secret|token)\s*[:=]/i.test(v);
const record = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const envelopeFields = ['schema_version', 'publication', 'report_id', 'date', 'kind', 'generated_at', 'cutoff', 'report_sha256', 'status', 'markets', 'content_sha256'].sort();
const itemFields = ['evidence_id', 'market', 'source_url', 'publisher', 'published_at', 'time_precision', 'event_date', 'source_sha256', 'claim', 'claim_sha256', 'claim_en', 'claim_en_sha256', 'applicability'].sort();
const exactFields = (value: Record<string, unknown>, fields: string[]): boolean => Object.keys(value).sort().join(',') === fields.join(',');
const stamp = (v: unknown): v is string => typeof v === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));
const date = (v: unknown): v is string => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v) && Number.isFinite(Date.parse(v)) && new Date(v).toISOString().slice(0, 10) === v;
const digest = (v: string): string => createHash('sha256').update(v, 'utf8').digest('hex');

function itemValid(item: unknown, market: string, cutoff: string): item is AsiaNewsItem {
  if (!record(item) || !exactFields(item, itemFields) || item.market !== market || !text(item.claim) || !text(item.publisher) || !text(item.source_url)
    || !/^asia\.[a-f0-9]{64}$/.test(String(item.evidence_id)) || !hash.test(String(item.source_sha256))
    || item.claim_sha256 !== publicReportIdentity(item.claim) || !['eligible', 'holiday_context'].includes(String(item.applicability))) return false;
  const url = new URL(item.source_url);
  if (url.protocol !== 'https:' || url.username || url.password || url.hash || (url.port && url.port !== '443')
    || !url.hostname.includes('.') || /^[\d.]+$/.test(url.hostname) || url.hostname.includes(':') || /(?:token|password|secret|api_key)=/i.test(url.search)) return false;
  if (item.claim_en === null ? item.claim_en_sha256 !== null : !text(item.claim_en) || item.claim_en_sha256 !== publicReportIdentity(item.claim_en)) return false;
  if (item.event_date !== null && !date(item.event_date)) return false;
  if (item.time_precision === 'timestamp') return stamp(item.published_at) && Date.parse(item.published_at) <= Date.parse(cutoff);
  return item.time_precision === 'date' && date(item.published_at) && item.published_at < cutoff.slice(0, 10);
}

export function validateAsiaNews(value: unknown, reportId: string, markdown: string): AsiaNewsPublicArtifact {
  if (!record(value) || !exactFields(value, envelopeFields) || !/^\d{4}-\d{2}-\d{2}-evening$/.test(reportId)
    || value.schema_version !== 'market_intel.asia_news_public.v1' || value.publication !== 'public'
    || value.report_id !== reportId || value.date !== reportId.slice(0, 10) || value.kind !== 'evening'
    || value.report_sha256 !== digest(markdown) || !stamp(value.generated_at) || !stamp(value.cutoff)
    || value.cutoff !== `${reportId.slice(0, 10)}T19:00:00+08:00` || Date.parse(value.generated_at) < Date.parse(value.cutoff)
    || !record(value.markets) || Object.keys(value.markets).sort().join(',') !== 'cn,hk') throw new Error('invalid public Asia news identity');
  const { content_sha256, ...body } = value;
  if (content_sha256 !== publicReportIdentity(body)) throw new Error('Asia news content hash mismatch');
  const items: AsiaNewsItem[] = [];
  const markets: { cn: AsiaNewsItem[]; hk: AsiaNewsItem[] } = { cn: [], hk: [] };
  for (const market of ['cn', 'hk'] as const) {
    const rows = value.markets[market];
    if (!Array.isArray(rows) || rows.length > 10 || !rows.every(row => itemValid(row, market, value.cutoff as string))) throw new Error('invalid public Asia news items');
    markets[market] = rows; items.push(...rows);
  }
  if (new Set(items.map(item => item.evidence_id)).size !== items.length
    || new Set(items.map(item => `${item.market}:${item.source_url}`)).size !== items.length
    || value.status !== (items.length ? 'reviewed' : 'missing')) throw new Error('invalid public Asia news status');
  return { ...Object.fromEntries(envelopeFields.map(key => [key, value[key]])), markets } as unknown as AsiaNewsPublicArtifact;
}

export function loadAsiaNews(reportId: string): AsiaNewsPublicArtifact | null {
  if (!/^\d{4}-\d{2}-\d{2}-evening$/.test(reportId)) throw new Error('invalid Asia news report ID');
  const root = realpathSync(dataRoot()), file = path.join(root, 'data/asia_news', `${reportId}.json`);
  if (!existsSync(file)) return null;
  const report = path.join(root, 'reports', `${reportId}.md`);
  if (![file, report].every(v => realpathSync(v).startsWith(root + path.sep))) throw new Error('Asia news path escapes public root');
  return validateAsiaNews(JSON.parse(readFileSync(file, 'utf8')), reportId, readFileSync(report, 'utf8'));
}

export function newsPresentation(item: AsiaNewsItem, locale: Locale) {
  const index = locale === 'en-US' ? 1 : 0;
  const sourceTime = item.time_precision === 'date' ? item.published_at : new Intl.DateTimeFormat(locale, {
    timeZone: item.market === 'cn' ? 'Asia/Shanghai' : 'Asia/Hong_Kong', year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(item.published_at));
  return { claim: locale === 'en-US' ? item.claim_en ?? item.claim : item.claim, href: item.source_url, sourceTime,
    timezone: item.market === 'cn' ? 'Asia/Shanghai' : 'Asia/Hong_Kong',
    precisionNote: item.time_precision === 'date' ? ASIA_NEWS_LABELS.dateOnly[index] : '',
    translationNote: locale === 'en-US' && item.claim_en === null ? ASIA_NEWS_LABELS.translationMissing[index] : '',
    contextNote: item.applicability === 'holiday_context' ? ASIA_NEWS_LABELS.holiday[index] : '' };
}
