export type FactQuality = string;

export interface MarketFact {
  id: string;
  value: number;
  observation_date: string;
  quality: FactQuality;
  source?: string;
  source_url: string;
  instrument?: string;
  metric?: string;
  unit?: string;
}

export interface MarketClaim {
  claim: string;
  evidence_ids: string[];
  sources: string[];
}

export interface MarketSection {
  key: string;
  claims?: string[];
}

export interface MarketSourceStatus {
  quality?: FactQuality;
  reason?: string;
  reviewed_movers?: Array<{ ticker: string; evidence_id: string }>;
}

export interface MarketDailyPayload {
  schema_version: string;
  run_id: string;
  facts: MarketFact[];
  as_of?: string;
  generated_at?: string;
  events?: MarketEventEvidence[];
  claims?: MarketClaim[];
  sections?: MarketSection[];
  missing_sources?: string[];
  report_formats?: string[];
  quality_summary?: { status?: string; revision?: string; market_revision?: string; news_revision?: { news_cutoff: string; revised_at: string } };
  source_status?: Record<string, MarketSourceStatus | undefined>;
}

export interface MarketEventEvidence {
  id: string;
  source_time?: string | null;
  publication_precision?: string;
  source_date?: string;
  source_timezone?: string;
  time_role?: string;
  usage?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

export function isMarketDailyPayload(value: unknown): value is MarketDailyPayload {
  return isRecord(value)
    && typeof value.schema_version === 'string'
    && typeof value.run_id === 'string'
    && Array.isArray(value.facts)
    && value.facts.every((item) => isRecord(item) && typeof item.id === 'string');
}

export interface MarketDailyRow {
  id: string;
  label: string;
  value: number;
  observationDate: string;
  sourceUrl: string;
  sourceLabel: string;
  instrument?: string;
  metric: string;
  unit: string;
  quality: FactQuality;
  text?: string;
}

export interface MarketClaimSummary {
  text: string;
  sourceUrls: string[];
  sectionKey: string;
  publication?: MarketEventEvidence[];
}

export interface MarketClaimSection {
  key: string;
  title: string;
  claims: MarketClaimSummary[];
}

export interface MarketDailySummary {
  date: string;
  rows: MarketDailyRow[];
  rateRows: Array<{
    tenor: string;
    label: string;
    levelValue: number | null;
    changeValue: number | null;
    observationDate?: string;
    sourceUrl?: string;
    sourceLabel?: string;
  }>;
  crossAssetRows: Array<{
    name: string;
    label: string;
    priceValue: number;
    priceUnit: string;
    changeValue: number;
    observationDate: string;
    sourceUrl: string;
    sourceLabel: string;
  }>;
  equityRows: Array<{
    symbol: string;
    priceValue: number;
    changeValue: number;
    observationDate: string;
    sourceUrl: string;
    sourceLabel: string;
  }>;
  claims: MarketClaimSummary[];
  claimSections: MarketClaimSection[];
  primaryClaims: MarketClaimSection[];
  secondaryClaimSections: MarketClaimSection[];
  secondaryRows: MarketDailyRow[];
  gaps: string[];
  optionalGaps: string[];
  hasTextReport: boolean;
  nextMorningRevision: boolean;
  historicalBackfill: boolean;
  newsRevision?: { factCutoff: string; newsCutoff: string; revisedAt: string };
  missingNewsSections?: string[];
}

export interface MarketDailyChartRow extends MarketDailyRow {
  side: 'level' | 'negative' | 'positive';
  width: number;
  valueText: string;
}

export interface MarketDailyChart {
  title: string;
  unit: string;
  prefix?: string;
  kind?: 'level';
  rows: MarketDailyChartRow[];
}
