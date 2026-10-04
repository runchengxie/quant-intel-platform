# 美股日报来源复核

`dm research` 只生成仓库外的私有候选草稿，不会把新闻写入正式报告。草稿的 `accepted_count` 表示结构与日期检查通过，不表示原文已核实。

逐条打开原文核对数字、解释、报道时间和盘中／收盘口径后，在仓库外建立审核 JSON：记录 `market_date`、原草稿文件 SHA-256、审核人，以及每条候选的 `index`、`status` 和 `reason`。`status` 只能是 `approved`、`deferred` 或 `rejected`；通过的候选还需单独撰写 `approved_summary`。指数涨跌要逐项记录 `index_returns` 及对应 `index_evidence`（`reported_change`、原文定位），目前只接受 AP 原站或 ABC News 上的 AP 报道。草稿变化或有候选未处置时，正式报告拒绝导入。

公司新闻优先核实至少三家不同公司的原始公告，材料不足时少写，不拿未经核实的条目凑数。`approved_summary` 用自然、简洁的中文重写，保留准确数字、时间和必要归因，使用中文标点，避免翻译腔、无依据的因果关系和套话。涨跌个股如需加入收盘价，在已通过审核的 `gainers` 或 `losers` 决策中填写明确的 `ticker`（1 至 5 位大写英文字母）；不从新闻叙述自动猜代码。行情另按报告日抓取，同日收盘价和日涨跌必须同时取得。

报告的 `source_status.equities.reviewed_movers` 会保留代码与审核证据 ID 的对应关系，供部署校验和公开页面导入核对。固定六只核心股以外的行情，没有这条对应关系就不能发布。核心六股有缺项时保留已核实的成对报价，并标记股票行情降级，不用旧值补齐。

当日的正式命令：

```bash
uv run dm daily-report --date YYYY-MM-DD --out /private/staging \
  --reviewed-draft /private/research/draft.json \
  --reviewed-decisions /private/research/review.json
```

纽约时间次日 09:30 前可用同一命令修订前一个报告日；必须同时提供草稿和审核单。修订报告保留原报告日，`as_of` 记录实际重新核实时间，`quality_summary.revision` 标记 `next_morning_rechecked`，`reviewed_source_cutoff` 记录新闻截点。它不是历史数据 vintage 快照；不可把次日才出现的材料说成前一日收盘时已可得。

收益率日变动优先取美国财政部同一交易日与前一观测日的官方 CSV；官方数据缺失才回退 FRED，并按原始观测日标记当日或滞后。财政部 CSV 不提供逐行发布时间，因此该来源的 `source_time` 记录本次读取时间，而非声称为官方发布时间。指数数字来自逐条复核的报道，不是可持续再发布的授权行情流。正式公开仍须经过部署仓库校验与 `publication: public` 清单，再由独立美股 Pages 发布通道导入。

## Offline news-only revisions

Use this path to append reviewed news while retaining the original market facts.
The ordinary command above fetches market data again. Development of the offline
path does not activate production delivery or replace any published report.

```bash
dm daily-report --date YYYY-MM-DD --revise-news /private/original/daily_report.json \
  --input-manifest /private/original/publication.json \
  --reviewed-draft /private/research/draft.json \
  --reviewed-decisions /private/research/review.json \
  --out /private/new-staging-directory
```

The input manifest must explicitly declare `publication: public` and match the
original report's bytes and content hash. Choose a new staging directory outside
source repositories. It must not overlap the report/manifest directory or contain
an input review file. `--backfill` cannot be combined with `--revise-news`.
`--news-cutoff` accepts a timezone-aware ISO timestamp and defaults to the actual
revision time. It cannot exceed that time.

Each approved decision additionally requires `source_locator`, `verified_facts`,
and private `display_basis` with `basis`, `scope`, `source_url`, `verified_on`.
The URL must match the candidate. Review source use independently of factual
accuracy. A reachable webpage alone does not establish a display basis. These
private review records are not published. `verified_on` is the UTC calendar date
of the review. A review may occur after the declared news cutoff, but cannot
postdate revision assembly. All candidates need a decision, and
any `index_returns`, `index_evidence`, or `ticker` instruction is rejected in this
mode, including instructions on deferred candidates.

For date-only macro/company background, use `publication_precision: date`,
`source_date: YYYY-MM-DD`, an independently verified IANA `source_timezone` or
`unknown`, explicit `time_role`, and `usage: background`. Omit `published_at`.
The complete possible publication interval must precede the news cutoff. Unknown
timezone uses UTC+14 through UTC-12 bounds. No minute or midnight is invented.
Filing acceptance remains labelled as filing acceptance. Date-only sources cannot
support close/mover quotations or closing causality.

The staged report uses schema `1.1`, retains the complete facts and original
`as_of`, and records the assembly time in `generated_at`. It preserves genuine
non-research gaps. `quality_summary.news_revision` records the original byte hash,
previous content hash, news cutoff and revision time. Later revisions retain an
append-only history. Reapplying identical evidence produces no output or new
timestamp. Conflicting evidence under the same hash-bound identity is rejected.
If the input was a historical backfill or next-morning market recheck,
`quality_summary.market_revision` retains that original provenance independently
of the new `news_only` label. This does not indicate a new market fetch.

Staging includes `daily_report.json`, `publication.json`, and a private immutable
`news_revision_parent.json`. Keep the parent for full-fact comparison and rollback.
The public importer discovers this sidecar or accepts `--previous-report PATH`.
It rejects a news-only transaction without the original artifact. Do not copy
the private parent into the public website. Deployment validation and controlled
promotion remain separate steps. This command does not invoke a supplier or model,
load provider credentials, send messages, change timers, or reset sent receipts.
