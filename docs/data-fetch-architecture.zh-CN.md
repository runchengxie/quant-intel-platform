[English page](data-fetch-architecture.md)

# 跨市场数据与报告架构

本文说明 `quant-intel-platform` 使用的跨市场数据链路。生产调度、凭证、服务单元和投递对象由私有仓库 `quant-intel-deploy` 管理。本公开仓库提供可复用的数据抓取、校验、报告和网站代码；GitHub Actions 用于质量检查和公开网站构建。

## 跨市场快照链路

晨报通过 `src/a_share_daily/cross_market.py` 获取跨市场数据：

1. 先读取 `data-snapshots/cross-market/` 下的指定日期快照，再尝试 `data-snapshots/latest/cross_market_snapshot.json`。设置 `CROSS_MARKET_SNAPSHOT_ROOT` 后，可改用稳定的外部快照目录。
2. 只接受日期不晚于目标日、且处于配置新鲜度范围内的快照。宏观和情绪数据观察日过旧时会产生新鲜度提示。
3. 没有可用快照时，实时抓取当前可获取的数据。设置 `CROSS_MARKET_FORCE_LIVE=1` 会跳过快照读取。
4. 某个可选数据源失败时保留部分结果和对应错误，不中断其余报告流程。

`src/a_share_daily/fallback_fetch.py` 提供按指定日期运行的同一套快照优先流程，并可将实时结果保存给后续调用者使用。生产任务必须使用部署环境配置的稳定数据路径，不能把数据写入临时 worktree。

输入包括美国和亚洲市场行情、大宗商品、宏观指标与情绪数据。韩国盘前和隔夜字段使用可选的数据源链；没有分钟行情时，这些字段仍是日线代理指标。产物会按契约保留来源和降级信息。

## 报告与网站边界

报告流程将跨市场结果作为带日期报告 manifest 的一项输入。报告生成会保留新鲜度提示和来源错误。跨市场数据用于信息参考，不构成交易指令。

公开网站由经过审查的已提交或上传产物构建。`public-site` workflow 构建网站和文档，不运行生产行情调度；`public-quality` workflow 执行仓库质量检查。真实凭证、定时任务、运行状态和报告投递由 `quant-intel-deploy` 负责。

## 关键实现路径

| 路径 | 职责 |
| --- | --- |
| `src/a_share_daily/cross_market.py` | 快照选择、新鲜度校验、实时跨市场抓取和报告输入 |
| `src/a_share_daily/fallback_fetch.py` | 快照优先抓取命令和快照持久化 |
| `src/a_share_daily/pipeline.py` | A 股报告编排 |
| `src/a_share_daily/morning_report.py` | 晨报组装 |
| `src/ops_common/paths.py` | 解析运维维护的数据与状态路径 |
| `src/ops_common/business_freshness.py` | 恢复流程中的跨市场快照新鲜度检查 |
| `.github/workflows/public-quality.yml` | 公开仓库质量门禁 |
| `.github/workflows/public-site.yml` | 公开网站和文档构建，以及从 `main` 部署 Pages |
| `quant-intel-deploy` | 私有生产配置、调度、密钥、运行状态和投递 |

生产操作手册和调度细节以 `quant-intel-deploy` 中的文档为准。不要根据公开网站 workflow 推断线上任务计划。
