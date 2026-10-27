# Language and localization policy

[Chinese version](LANGUAGE_POLICY.zh-CN.md)

`quant-intel-platform` keeps computation, source data, artifact schemas, and
delivery receipts language-neutral. Human-facing reports may be rendered in a
selected locale after the structured report model has been built.

The public locale identifiers are `en-US` and `zh-CN`. The default is
`en-US` for human-facing reports and the public documentation site. Locale is
independent from timezone, currency, market calendar, and numeric precision.
Unknown locale identifiers must fail fast instead of silently changing report
semantics.

Engineering identifiers, CLI flags, JSON keys, artifact contracts, and error
codes remain English or language-neutral. Do not put translated labels into
machine-readable artifacts. A renderer should accept a locale and translate
presentation labels only.

A-share morning and evening renderers select catalog templates before inserting
source fields. Titles, body templates, freshness summaries, known producer labels
and currency units support both locales. Labels are translated only when recognized
for their producer field. Missing catalog translations fall back
to English. An unknown locale is rejected.

News statements, titles, source names, evidence URLs, concept names and unknown
producer notes retain their source text. English reports state this explicitly;
English selection does not translate arbitrary source content. Locale selection
never rewrites the assembled report or its source statements, and does not modify
input payloads, calculations, artifact schemas or receipt identities. The morning
publication/import path retains warning classification and prior-close numeric
baselines in both locales. Warnings remain a list of source strings, capped at
12 entries. Distinct evidence paragraphs retain their warnings even when the
wording repeats across dates or paragraphs.

The public documentation has paired English and Chinese navigation; Pages has
its own route and fallback behavior.

When adding a localized surface, establish the structured report-model boundary
first, then cover deterministic rendering and CLI selection with tests. Keep
English as the canonical documentation language, maintain Chinese companions for
active public pages, and translate historical archives selectively.

There must be one report builder and multiple locale renderers, not one
independently maintained report pipeline per language.
