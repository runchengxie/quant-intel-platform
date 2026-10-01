# Asia evening image: published tables

The native SVG consumes the same evening Markdown shown in the existing full
report detail panel. It does not create a chart-source asset or claim that these
Markdown facts passed the separate per-point chart review.

The image keeps every parsable index row, its exact published close and turnover,
and a daily-return bar centered on zero. Index turnover overlaps and is never
summed. Industry and high-turnover tables preview five rows; concepts preview
five, and extreme movers retain the published top gainers and decliners. The
full Markdown remains the authoritative detail view for the remaining rows.

Missing values stay missing. Invalid index lines, table schemas and row lengths
are shown as explicit unparsed text rather than converted into numeric defaults.
Industry returns must be signed finite percentages (published unsigned zero is
accepted), counts must be nonnegative integers, and advancing shares must be
between 0 and 100 percent. Turnover stocks keep six-digit tickers, nonnegative
finite decimal amounts and signed returns. Concepts require a name, signed
return, source leader name with its percentage, and a nonnegative integer limit-up
count. Explicit `N/A` fields remain unchanged; invalid same-width rows stay out of
the numeric table and appear in fallback text. No economic upper bounds are added.
Existing sign-based `[OK]` and `[WARN]` tokens are omitted from the visual;
signed values and color convey direction independently of chart quality states.
Price-limit counts remain separate, and large-order proxy and missing/T+1 margin
wording are retained. Existing breadth and six-dimension charts are reused.

Chinese and English share parsing and layout. New labels use semantic keys in
`ASIA_IMAGE_LABELS` within the existing `locale.ts` catalog. The renderer selects
catalog labels directly; `english-content.ts` bridges legacy presentation text.
The optional fourth presentation function remains compatible with existing
callers. Production English callers pass the explicit fifth `en-US` locale;
language inference is retained only for legacy calls that omit it. Whole cell
labels and preview templates are translated before wrapping;
unknown company names and prose remain intact rather than being partly translated.
Concept-leader company names are preserved verbatim as source names, including
Chinese names in the English presentation.
All report text, including source attribution, is escaped for SVG.

Offline validation on 2026-10-01/02 uses the published 2026-09-30 evening report,
plus malformed/missing/escaped synthetic rows. Generated SVGs, browser captures
and validation logs are kept outside the repository under the task's data
validation directory. This change does not refresh public snapshots or publish
production output.
