# Market daily website

[中文页面](market-site.md)

Open the [market daily website](https://runchengxie.github.io/quant-intel-platform/). It organizes content around two Beijing-time windows: the US close at 07:00 and the Asia close at 19:00. The page shows the five most recent dates with reports; use the actual generation time, observation date, and missing-data notices as the source of freshness context.

The daily report and this documentation share a warm visual language, and both support light and dark themes. On first visit, the site follows the device appearance setting. The home page groups indices, equities, US Treasuries, and cross-asset data. Index sparklines use public observations whose observation date matches the report date.

Website code, build tools, and public snapshots live under `web/`. Production schedules and credentials are managed by the private deploy repository. Public GitHub Actions validate committed data and build the site; they do not fetch credentialed data or call models.

## Local preview

Use Python 3.11–3.13, Node.js 24, and npm. From the repository root:

```bash
cd web
npm ci
preview_root=$(mktemp -d /tmp/qmi-preview.XXXXXX)
python3 scripts/build_site.py --output "$preview_root/quant-intel-platform"
python3 -m http.server 8000 --directory "$preview_root"
```

Open <http://localhost:8000/quant-intel-platform/>. The builder recreates the requested output directory; do not point `--output` at a directory containing business data.

## Browser regression checks

After installing `web/` dependencies, install Chromium and run the public-sample browser tests:

```bash
cd web
npm ci
npx playwright install chromium
npm run test:browser
```

The command builds the Astro site, then checks the English entry at `/quant-intel-platform/en/` and the Chinese entry at `/quant-intel-platform/?locale=zh-CN`. It exercises three viewport widths, navigation, theme persistence, report SVG, PNG download, and historical evening reports. CI's build job uses `npx playwright install --with-deps chromium`. On failure it uploads screenshots and retry traces under `web/test-results/`; PR builds do not deploy Pages. These artifacts contain only public repository samples.

## Content sources

- `web/artifacts/public/` contains recently reviewed public data and reports. After site build, downloads remain under `/data/` and `/reports/`.
- `web/src/` contains Astro pages and archived legacy pages; `web/tests/` covers contracts and rendering.
- The `market_intel_publication` package imports reports and creates public snapshots. `market_intel_commentary` handles model-generated commentary. `web/scripts/` contains compatibility entry points, chart review, and static build logic. Authoritative market data and production scheduling are outside this website layer.
- Asia-close commentary first tries local Codex, then configured DeepSeek, Gemini, and MiniMax credentials. Consecutive evening reports may compare the latest with the prior report. Historical morning/evening pairs remain readable.

Private deployment configuration, receipts, and recovery procedures are in `quant-intel-deploy/docs/market-pages-publisher.md`. Website development details are in the [`web/docs/technical-guide.md`](https://github.com/runchengxie/quant-intel-platform/blob/main/web/docs/technical-guide.md).

## Online snapshot freshness

The public Asia-close index is [reports.json](https://runchengxie.github.io/quant-intel-platform/data/reports.json); the US report is [market_daily_report.json](https://runchengxie.github.io/quant-intel-platform/data/market_daily_report.json). At runtime, read both online JSON files and check the latest report's market date and original generation time. Health information from a static build does not represent current freshness.

Manually investigate if a report is more than 96 hours old, a snapshot cannot be read, or its time fields are invalid. Ninety-six hours is a conservative reminder threshold: holidays or other market closures may trigger it. It does not prove publication failure and should not block a website deployment by itself.

## Publication and freshness alerts

The `Public site monitor` workflow reads both online snapshots every six hours at 00:00, 06:00, 12:00, and 18:00 UTC. It maintains GitHub Issues tagged `public-site-alert` separately for the Asia-close and US reports. After the `Public website` workflow completes, monitoring processes only `main` and `automation/pages-*` branches: it alerts on failure and closes the corresponding issue when a later run on that branch succeeds. Before acting on a delayed build event, it compares the event with the latest completed run on that branch to avoid reopening a recovered alert. GitHub API errors in the monitor fail its Actions run and must be inspected directly.

Maintainers should subscribe to **Issues** and **Actions** under the repository's **Watch → Custom** settings and verify their personal GitHub notification delivery. Issues may not be proactively delivered without that subscription. When an alert arrives, verify the public snapshot report date and generation time, then check for a market closure or upstream publication issue. The issue contains a brief status and Actions link, not report content or raw HTTP responses.

For a manual check, open **Actions → Public site monitor → Run workflow**, keep `dry_run` enabled on `main`, and run it. This reads the online snapshots and prints a summary without creating, commenting on, or closing an issue. Disabling `dry_run` explicitly errors; manual issue writes are not supported. To inspect actual alerts, review scheduled monitoring runs or runs triggered after `Public website` completes, along with issues carrying `public-site-alert`. Do not manufacture a production failure to test notifications.
