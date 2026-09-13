# 数据目录说明

本机量化数据统一放在 `~/data/quant/`。其中，行情数据平台的主目录是
`~/data/quant/market-data-platform`。代码仓库通过 `DATA_PLATFORM_ROOT` 读取这个目录，
不直接依赖本机目录结构。

## 常用目录

| 目录 | 用途 | 处理原则 |
| --- | --- | --- |
| `assets/` | 原始行情和加工后的数据资产 | 由数据平台维护，按 manifest 和 receipt 使用 |
| `published/` | 已通过检查、可以供其他项目读取的数据 | 只保留当前版本和明确的回滚版本 |
| `metadata/` | 数据注册表、版本信息、校验记录和生命周期记录 | 与数据资产一起保留 |
| `reports/` | 健康检查、质量检查和发布报告 | 用于审计，不作为数据源 |
| `strategy_outputs/` | 策略生成的正式结果，例如 watchlist20 | 以 `latest` 和 receipt 指向的版本为准 |
| `strategy_inputs/` | 策略运行所需的输入材料 | 由对应生产任务生成和清理 |
| `staging/` | 补数、候选版本和验证中的中间结果 | 只有完成验收后才能归档 |
| `experiments/`、`runs/` | 研究实验和运行记录 | 保留 provenance、manifest 和结果 |
| `archive/` | 已退出日常使用范围的历史材料 | 迁移前先记录原路径和校验摘要 |

## 本次迁移结论

- 主数据根已经迁移到 `~/data/quant/market-data-platform`。
- 旧的 `~/data/market-data-platform` 目录当前不存在。
- 代码和调度模板应优先读取 `DATA_PLATFORM_ROOT`。本地脚本的默认值只用于开发机兜底。
- `quant-intel-platform` 只读取数据平台发布的资产和研究侧发布的 artifact，不把生产数据提交到代码仓库。
- 代码仓库里的 `out/` 和 `state/` 可能保存历史运行路径。这些路径属于当时的回执和审计记录，不能批量改写。

## 当前待处理项

- `staging/` 中仍有多个候选版本和补数目录。处理前需要确认终态 receipt、锁文件、运行进程、
  `current`、`latest`、`rollback` 和正式替代物。
- `assets/tushare/a_share/` 下的空文件 `=0.9`、`=3.8` 看起来像临时残留。它们目前只做记录，
  暂不删除，待确认来源后再移入可回收区。
- 数据审计报告位于 `~/data/.audit/`。审计结果只提供整理线索，不直接授权删除。

## 运行前检查

```bash
test -d "${DATA_PLATFORM_ROOT:-$HOME/data/quant/market-data-platform}"
find "${DATA_PLATFORM_ROOT:-$HOME/data/quant/market-data-platform}" -maxdepth 1 -type d | sort
```

生产调度由 `quant-intel-deploy` 管理。修改数据位置时，先更新部署环境中的
`DATA_PLATFORM_ROOT`，再重新生成 systemd 配置并执行本地检查。
