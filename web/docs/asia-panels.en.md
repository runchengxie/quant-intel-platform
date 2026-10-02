# Asia report panels and source gaps

The new market-overview, price-limit and flow graphics consume the already-published evening Markdown. They do not fetch private data or recalculate market facts. Signed return bars share a zero axis. Advancing/declining/unchanged counts form one disjoint group; price-limit and beyond-5% counts are separate overlapping comparisons. Large-order flow remains a proxy, not identified institutional trading. Malformed rows retain the original text without fabricated bars. New labels live in the semantic locale catalog.

The weekly input window now uses the authoritative SSE open-session calendar. September 30, 2026 has September 23, 24, 28, 29 and 30 as its preceding five sessions. A missing calendar fails explicitly instead of guessing weekdays. Missing open-session partitions remain gaps and are not silently replaced by older observations.

Financing-history rows use the intersection of exchange coverage across the plotted observations. The source label states that scope and partial coverage keeps the public candidate degraded even when its observation date is current. Private plots identify their exchange scope. Unknown legacy scope is explicitly unverified. Recovering missing exchange rows belongs to the data owner, not the report renderer.

The inspected public September 30 financing chart was generated before the October 1 private report rerun. A code merge does not refresh or approve that snapshot. A revised source candidate needs the normal fact/rights review and controlled publication, with no resend of an already-delivered report.

Asia news is a separate proposed subsystem in `docs/superpowers/specs/2026-10-02-asia-news-design.md`. It is not enabled by these changes. Production runtime pins, scheduler configuration, source data and personal delivery receipts are unchanged.
