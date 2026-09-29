import { createHash } from 'node:crypto';

function sortedJson(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortedJson);
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).sort(([left], [right]) =>
      left < right ? -1 : left > right ? 1 : 0).map(([key, item]) => [key, sortedJson(item)]));
  }
  return value;
}

/** Match the publisher's json.dumps(sort_keys=True, ensure_ascii=False, separators=(',', ':')). */
export function publicReportIdentity(report: unknown): string {
  return createHash('sha256').update(JSON.stringify(sortedJson(report)), 'utf8').digest('hex');
}
