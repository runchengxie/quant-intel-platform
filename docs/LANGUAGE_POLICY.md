# Language and localization policy

`quant-intel-platform` keeps computation, source data, artifact schemas, and
delivery receipts language-neutral. Human-facing reports may be rendered in a
selected locale after the structured report model has been built.

The public locale identifiers are `en-US` and `zh-CN`; `zh-CN` remains the
default during the migration. Locale is independent from timezone, currency,
market calendar, and numeric precision. Unknown locale identifiers must fail
fast instead of silently changing report semantics.

Engineering identifiers, CLI flags, JSON keys, artifact contracts, and error
codes remain English or language-neutral. Do not put translated labels into
machine-readable artifacts. A renderer should accept a locale and translate
presentation labels only.

The migration order is:

1. stabilize the locale contract and report-model boundary;
2. localize one deterministic renderer with snapshot coverage;
3. add locale selection to CLI and publication surfaces;
4. migrate web and delivery adapters;
5. translate active documentation, then historical archives selectively.

There must be one report builder and multiple locale renderers, not one
independently maintained report pipeline per language.
