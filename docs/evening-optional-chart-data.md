# Missing optional evening concept charts

An evening review may have no available same-day concept-sector dataset. The
loader returns `hot_sectors: {}` only for a missing partition or an empty dataset.
Malformed/corrupt inputs and invalid columns raise an error rather than being
silently interpreted as absence. A historical empty fallback does not establish
why the old data read failed; inspect the owner partition before recovery.

Evening public extraction treats an absent `hot_sectors` field or an empty object
as optional missing data. The manifest sets an empty topic point list, removes
retained topic `ok`/`degraded` flags and records `charts.missing: ["topic"]`.
Export uses the existing six-chart schema with topic `status: missing`, no points
and reason `当日概念板块数据暂缺`. No data or source observations are fabricated.
The public importer and snapshot exporter preserve the standard missing card;
website consumers can display the reason using their existing missing-card flow.

An explicit malformed/nonempty object, missing/wrong-type `top_by_change`, fewer
than five rows, invalid numeric values, wrong report date or missing required
six-dimension market-temperature data remains blocking. Empty optional concepts
do not change the validation of essential market facts. Industry statistics are
a separate review dataset and are not substituted for concept-sector points.

When an old review has an empty concept fallback but the owner now has verified
same-day concept data, regenerate the review through the normal production
recovery process. Keep the historical failure and original review intact.
