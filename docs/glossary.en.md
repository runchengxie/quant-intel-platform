# Glossary

[中文页面](glossary.md)

This glossary explains abbreviations and mixed Chinese/English terminology used in the documentation. Code identifiers, provider names, frameworks, and ticker symbols remain in English.

## Abbreviations

Spell out each abbreviation in Chinese at its first occurrence in a Chinese document.

| Abbreviation | English expansion | Chinese term |
| --- | --- | --- |
| ADR | Architecture Decision Record | 架构决策记录 |
| CLI | Command-line interface | 命令行 |
| CI/CD | Continuous Integration / Continuous Delivery | 持续集成与持续交付 |
| PR | Pull request | 拉取请求 |
| ETL | Extract, Transform, Load | 数据抽取、转换与加载 |
| API | Application Programming Interface | 应用程序接口 |
| TA | Technical analysis | 技术分析 |
| LLM | Large language model | 大语言模型 |
| OOS | Out of sample | 样本外 |
| CST | China Standard Time | 中国标准时间 |
| ET | Eastern Time | 美国东部时间 |
| UTC | Coordinated Universal Time | 协调世界时 |
| PE | Price-to-earnings ratio | 市盈率 |
| EPS | Earnings per share | 每股收益 |
| TTM | Trailing twelve months | 过去十二个月滚动 |
| NTM | Next twelve months | 未来十二个月 |
| SMA | Simple moving average | 简单移动平均 |
| RSI | Relative strength index | 相对强弱指标 |
| ATR | Average true range | 平均真实波幅 |
| PIT | Point in time | 时点信息；数据在真实可用时刻的快照 |
| EOD | End of day | 日终 |
| PSR | Probabilistic Sharpe ratio | 概率夏普比率 |
| DSR | Deflated Sharpe ratio | 修正夏普比率 |
| Rank IC | Rank information coefficient | 截面排序信息系数 |
| gitlink | Git submodule pointer | Git 子模块指针 |

## Preferred Chinese prose terms

Use the Chinese term in Chinese prose and retain English only in code identifiers, filenames, CLI options, or when introducing the technical term.

| English term | Preferred Chinese term |
| --- | --- |
| fallback | 兜底 |
| snapshot | 快照 |
| contract | 契约 |
| manifest | 清单 |
| token | 令牌 |
| hook | 钩子 |
| namespace | 命名空间 |
| submodule | 子模块 |
| pipeline | 流水线 |
| dashboard | 看板 |
| idempotency / idempotent | 幂等 |
| degraded | 降级 |
| handoff | 交接 |
| deploy / deployment | 部署 |
| preview | 预览 |
| delivery | 投递 |
| repo | 仓库 |
| cron | 定时任务 |
| provider | 数据提供方 |
| deferred stub | 延迟占位 |
| registry | 注册表 |
| receipt | 回执 |
| panel | 面板; for factor data, a cross-sectional matrix |
| live ETL | 实时 ETL; online extraction, transformation, and loading, contrasted with offline snapshots |
| fail closed | 严格失败即止; reject rendering or delivery when validation fails rather than allowing degraded output |

## Names that remain in English

- Providers and frameworks: TuShare, FMP, Alpha Vantage, FRED, EDGAR, AAII, CBOE, OANDA, yfinance, GLM, Qwen, DeepSeek.
- Platforms and code: GitHub, GitHub Actions, Feishu/Lark, Hermes, systemd, PowerShell, Pages, OIDC.
- Financial symbols: VIX, VVIX, SPY, QQQ, SMH, GLD, SLV, GC=F, DXY, HSI, BTC, XAU, A-share.
- Data formats: JSON, CSV, YAML, RSS/Atom.

## Project-specific names

These names correspond to code directories, Feishu groups, or bots. Explain them without renaming the underlying identifiers.

| Name | Meaning |
| --- | --- |
| `hotsector` | Abbreviation for the former hot-sector screener and the list it produced |
| Hermes | Feishu/Lark-based message-delivery layer for sending reports |
| DailyWatch / DailyWatch20 | A daily list of 20 A-share securities |
| `lark-cli` | Feishu/Lark command-line client used by delivery scripts |
| `watchlist20` | Strategy-layer artifact/command for a 20-security watchlist; equivalent to DailyWatch20 |
| AI精选 | Chinese product name for the list formerly produced by `ai-stock-picker` |
| Mag7 | Magnificent Seven, the seven large US technology companies: Apple, Microsoft, Alphabet, Amazon, NVIDIA, Meta, and Tesla |
| Numeric ranking | A numeric scoring and sorting method |
| Five-arm stability experiment | Research design that runs five arms on the same frozen data using a Latin-square design to reduce order bias and check model-output stability |
| Hermite | Stability guard, a transformation applied above factors for the B sleeve; distinct from Hermes, the delivery layer |

There is no project component named Numeric Shadow. Numeric ranking and the five-arm stability experiment are separate concepts.

## Research-state terminology

The following terms describe research states in documents such as `configuration.md` and `report-distribution.md`; they do not imply production release:

| Term | Meaning |
| --- | --- |
| `research_only` | Compute and record evidence, but do not render, send, or include it in production reports |
| `shadow` | Run new logic alongside the existing path and generate comparisons without replacing production |
| pick-plan / trial | A paired experiment using frozen inputs and configuration to reproduce a run under fixed conditions |
| append-only evidence | Record experiment results by appending rather than overwriting, preserving run history |
| Pro+thinking | A higher-cost deep-reasoning model configuration not covered by every experiment |
