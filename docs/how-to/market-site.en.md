# Market reports website

[Chinese version](market-site.md)

Open the [market reports website](https://runchengxie.github.io/quant-intel-pages/). Pages displays the latest five report dates, source links, and downloadable reports. This repository owns report generation and review; the separate [`quant-intel-pages`](https://github.com/runchengxie/quant-intel-pages) repository owns the Astro frontend, static rendering, hosting, and live freshness monitoring.

The platform's `market_intel_publication` package validates reports and versioned public data contracts, then exports snapshots for Pages. `quant-intel-deploy` owns production publication, receipts, and recovery. The public site reads only reviewed artifacts explicitly marked for publication.

The Asia report index is [reports.json](https://runchengxie.github.io/quant-intel-pages/data/reports.json); the US daily report index is [market_daily_report.json](https://runchengxie.github.io/quant-intel-pages/data/market_daily_report.json). See the Deploy repository's [market report publisher guide](https://github.com/runchengxie/quant-intel-deploy/blob/main/docs/market-pages-publisher.md) for production configuration and recovery.
