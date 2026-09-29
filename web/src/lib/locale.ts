export const SUPPORTED_LOCALES = ['en-US', 'zh-CN'] as const;
export type Locale = typeof SUPPORTED_LOCALES[number];

export const LOCALE_PATHS: Record<Locale, string> = {
  'en-US': '/en/',
  'zh-CN': '/',
};

export function localePath(locale: Locale, base = ''): string {
  return `${base}${LOCALE_PATHS[locale]}`;
}
