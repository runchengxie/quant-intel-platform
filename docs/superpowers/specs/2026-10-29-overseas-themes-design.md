# Overseas theme observations and research evidence

Approved scope: P0 observation semantics and timing, P1 independent semiconductor study in
quant-market-research, P2 versioned research evidence consumed by reports. No production deployment.

The existing human-weighted foreign equity averages describe observations, not calibrated A-share
forecasts. Keep legacy machine keys for compatibility but never derive prediction confidence from them.
Version the mapping; retain source URLs, session dates and evidence IDs. Missing, future, non-finite or
stale quotes must not contribute at a decision cutoff. Exchange calendars determine eligible sessions.
A-share report context uses Asia/Shanghai and distinguishes pre-open, intraday, post-close and holidays.

Research owns models and immutable experiment outputs. Reports consume only the versioned
`overseas_theme_evidence.v1` JSON with a pinned SHA-256, validate schema, dates, revision and sources,
and show retrospective sample/error/interval/limitations separately from today's observations.
No ETF recommendations until an owner supplies verified product and dated holdings evidence.
Absent or rejected evidence degrades to observations, with a visible reason. English and Chinese
presentation text belongs in locale catalogs. Existing forward-v1 remains unchanged.

Approaches: only relabeling would leave invalid inputs and cross-repo evidence unaddressed; copying
research into reports would violate ownership. Selected: calendar-qualified observations plus a
versioned file boundary, independently verified provider and consumer.
