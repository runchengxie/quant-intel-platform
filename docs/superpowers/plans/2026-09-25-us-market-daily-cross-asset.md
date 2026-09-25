# 美股日报聚焦与跨资产行情实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为日报结构化产物补齐美债收益率水平与 Brent/金银/比特币连续期货行情，并为网页提供精简、可核查的美股收盘摘要。

**Architecture:** `quant-intel-platform` 作为 provider 生成日期严格对齐的 Treasury/Yahoo 事实，并显式表达单项失败；provider 先合并。之后 `market-intel-pages` 扩展公开事实白名单和校验，主页突出短摘要、全文保留宏观/公司材料，并用合并后的 provider artifact 生成/导入 2026-09-24 交易日报。

**Tech Stack:** Python 3.13、pytest、`requests`、既有 Yahoo chart fetcher、JavaScript ESM/CJS 共享工具、Astro/GFM、GitHub Pages。

**Spec:** `docs/superpowers/specs/2026-09-25-us-market-daily-cross-asset-design.md`

## Global Constraints

- 报告事实必须带 source URL、source/retrieved time、quality、unit 和 observation_date。
- Treasury level 与 change 必须来自同一日期行和前一有效美国交易日行。
- 商品连续期货代码固定为 `BZ=F`、`GC=F`、`SI=F`、`BTC=F`，摘要只接受观察日等于报告日的点。
- 缺数、延迟、数据错误不得以 0、旧值或模型猜测填充。
- 只公开审核过的结构化事实和 claim；用户截图授权由用户确认但不在本环境可见。
- provider PR 必须先于 consumer PR 合并。

## Review Focus

- Yahoo 日线时间戳若映射到不同美东日期，必须明确标 missing，而非挪到目标日。
- 连续期货换月时价格可能跳变；报告标注连续期货代理与 ticker，不声称现货/正式结算价。
- Treasury CSV 节假日、周末和跨月时，previous 必须是前一有效观测日。
- 单一商品 endpoint 失败不能删除其他资产成功点。
- 页面正文、PNG 图、Markdown 和纯文本不能出现不同观察日/单位或漏掉缺数 caveat。

---

### Task 1: Provider Treasury observation model

**Files:**
- Modify: `src/daily_messenger/daily_report/treasury.py`
- Modify: `src/daily_messenger/daily_report/macro.py`
- Test: `tests/daily_report/test_treasury.py`
- Test: `tests/daily_report/test_live_macro.py`

**Interfaces:**
- Produces the official daily Treasury observation map by date and tenor, retaining the existing `fetch_treasury_yield_changes(date)` wrapper for callers.
- Emits `treasury.{2y,5y,10y,30y}.level_percent` and existing `.change_bp` facts with identical source date/URL.

- [ ] Add tests that parse current and previous CSV rows across weekends/month boundaries, derive exact levels and bp changes, and reject a missing/invalid tenor.
- [ ] Run the focused Treasury tests and confirm failures occur because the observation-level interface/facts are absent.
- [ ] Implement a single fetch/parse path that returns current and prior valid rates, then build level and change facts from that result.
- [ ] Add fallback tests for FRED levels when the official CSV is unavailable and preserve lagged quality/observation_date rules.
- [ ] Run `uv run pytest tests/daily_report/test_treasury.py tests/daily_report/test_live_macro.py`.
- [ ] Commit the independently testable provider change.

### Task 2: Provider cross-asset Yahoo futures

**Files:**
- Modify: `src/daily_messenger/etl/fetchers/quotes.py`
- Create: `src/daily_messenger/daily_report/cross_asset.py`
- Modify: `src/daily_messenger/daily_report/pipeline.py`
- Test: `tests/daily_report/test_cross_asset.py`
- Test: `tests/daily_report/test_live_macro.py`

**Interfaces:**
- Add a public daily-report Yahoo history helper returning symbol, NY observation date, close, previous close, return percent and source URL.
- Build separate price and return facts such as `cross_asset.brent.close` and `cross_asset.brent.change_percent`; include ticker identity in `instrument`, native USD units, source fields, and observation date.
- Add `cross_asset` source_status and missing source only for incomplete tickers; use a distinct `cross_asset` section referencing available fact IDs.

- [ ] Test the four configured symbols, exact return math, source URLs, observation dates, non-finite/zero previous close, date mismatch, and per-symbol failure isolation.
- [ ] Verify the tests fail because no cross-asset provider/report section exists.
- [ ] Implement a small fetch function reusing the existing Yahoo chart transport/parsing helpers without triggering unrelated provider fallback.
- [ ] Add all-success, partial-success and all-failure report tests; ensure fixture mode remains explicitly non-publishable.
- [ ] Run focused tests and `uv run pytest tests/daily_report`.
- [ ] Commit the provider feature and update the spec/plan if actual Yahoo timestamps require a changed explicit rule.

### Task 3: Merge provider and verify dated artifact

**Files:**
- Modify: provider PR only; no consumer files until provider main is updated.
- External artifact: private daily report + review receipt outside Git.

- [ ] Run `uv run python project_tools/check_all.py --scope all` and all daily-report-specific tests.
- [ ] Request independent review of provider source/date/quality behavior, fix any material finding, open provider PR and wait for required checks/review.
- [ ] Merge provider PR only after checks and review pass.
- [ ] Generate the `2026-09-24` artifact from merged provider code, independently verify values against dated raw source rows/pages, and preserve private review evidence outside Git.

### Task 4: Consumer contract and compact report renderer

**Files (consumer repository, new branch after provider merge):**
- Modify: `scripts/import_market_daily_report.py`
- Modify: `market-daily-utils.js`
- Modify: `app.js`, `index.html`, `styles.css`
- Modify: `tests/test_import_market_daily_report.py`, `tests/market-daily-utils.test.cjs`, `tests/astro-pages.test.cjs`
- Update: `data/market_daily_report.json`, generated `reports/2026-09-24-market-daily.md` and `.txt` through importer only after source audit.

- [ ] Add failing contract tests for new level/commodity facts, source allowlist, source date matching and required units.
- [ ] Add failing renderer tests for compact index/rates/cross-asset layout, maximum 3 driver claims and an accessible collapsed full-detail area.
- [ ] Implement public fact mapping/validation; preserve existing fact schema and reject unrecognized or future facts.
- [ ] Implement the compact default view and collapsible macro/company details; keep the full Markdown/HTML report text available for download.
- [ ] Import the merged-provider, privately reviewed 2026-09-24 report with preview then apply; do not edit generated Markdown by hand.
- [ ] Run the full Python/Node tests, `python3 scripts/build_site.py --output /tmp/us-daily-cross-asset-site`, rendered desktop/narrow checks and visual inspection.
- [ ] Open consumer PR only after provider main contains the producing contract and dated payload is independently validated; merge and verify production URL/data hash.

### Task 5: Production update and handoff

- [ ] Publish/activate the merged provider release through the existing stable deployment path; do not change scheduler cadence.
- [ ] Verify deployment health, daily-report CLI, fresh source dates and public page rendering without sending Feishu messages.
- [ ] Record both PR links, merge SHAs, deployment identity, observed gaps and cleanup status; remove only this task's merged branches/worktrees.
