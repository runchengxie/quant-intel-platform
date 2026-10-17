# 配置说明

[English page](configuration.md)

配置分为两部分：仓库内的公开默认值，以及部署环境提供的运行参数。

## 公开安全的环境变量

以下是非密钥的部署路径和受众标识示例：

```bash
MARKET_INTEL_CLIENT_CHAT_ID=example_client_target
MARKET_INTEL_INTERNAL_CHAT_ID=example_internal_target
MARKET_INTEL_PUBLIC_CHAT_ID=example_public_target
DATA_PLATFORM_ROOT=/path/to/local/data
A_SHARE_OUTPUT_DIR=/path/to/report/output
A_SHARE_DELIVERY_STATE_DIR=/path/to/delivery/state
SCHEDULED_RECOVERY_STATE_ROOT=/path/to/recovery/state
CROSS_MARKET_SNAPSHOT_ROOT=/path/to/cross-market/snapshots
```

上面的受众 ID 只是示例。目标未配置时，系统仍可执行离线渲染和 CI 测试，也不会发送消息。

`DATA_PLATFORM_ROOT` 是持久化运行数据的默认根目录。A 股报告默认写入
`$DATA_PLATFORM_ROOT/reports/market-intel/a_share_daily`；投递回执和计划恢复状态默认写入
`$DATA_PLATFORM_ROOT/state/market-intel/`。部署可以通过 `A_SHARE_OUTPUT_DIR`、
`A_SHARE_DELIVERY_STATE_DIR`、`SCHEDULED_RECOVERY_STATE_ROOT` 和
`CROSS_MARKET_SNAPSHOT_ROOT` 覆盖相应路径。持久化入口没有数据根目录，也没有所需的路径覆盖时，
会报配置错误并停止。

生产凭据和真实投递目标必须由部署环境注入。请勿提交令牌、私有路径、原始数据、回执或运行状态。

## 凭据

本地开发使用仓库根目录下 Git 忽略的 `api_keys.json`。首次配置时，将
`config/api_keys.json.example` 复制为 `api_keys.json` 并填入本机凭据。加载器也支持
`API_KEYS_PATH`、用户配置路径 `~/.config/market-intel/api_keys.json`，以及部分服务商环境变量。
CI 和部署应使用对应平台的密钥管理功能。不要通过 `.env` 模板分发凭据，也不要提交真实凭据或服务商数据快照。

API 密钥示例预留了顶层 `gold_api` 字段，对应
[gold-api.com](https://gold-api.com/)（不是 GoldAPI.io）。只在私有 JSON 凭证文件中替换
`YOUR_GOLD_API_KEY`。此占位不会启用数据适配器，也不会改变日报价格口径。

## 韩国市场回退数据

韩国日频代理行情不需要 API key。运行时依次尝试 FinanceDataReader、pykrx 和 yfinance，
并记录实际 `source`、设置 `degraded=true`。这些代理行情不代表 KRX 或 NXT 官方盘中数据。

## AI 市场资讯

AI 市场资讯支持智谱 GLM、阿里百炼和 Google Gemini。`api_keys.json` 的 `ai_news` 配置可以提供默认值；
服务商专用环境变量会覆盖对应设置。例如，`AI_NEWS_PROVIDER=aliyun` 与
`ALIYUN_MODEL=qwen3.7-flash` 会选择阿里百炼的 `qwen3.7-flash`，即使 JSON 中仍有通用的 `model` 字段。

每次抓取都会输出一条 `ai_news_runtime` 结构化日志，记录最终解析的 `provider`、`model`、`base_url`
和 `fallback_order`。日志不含 API key，可用于核对实际生效的服务商配置。

## 跨仓配置

工作流调用 owner CLI 时使用明确路径：

```bash
DATA_PLATFORM_ROOT=/path/to/data/market-data-platform
MDP_DIR=/path/to/quant-market-data-platform
QUANT_RESEARCH_ROOT=/path/to/quant-research
MARKET_INTEL_ROOT=/path/to/quant-intel-platform
```

仓库路径只用于启动进程，不是 Python 导入边界。owner CLI 执行后应校验产物与回执。
生产专用配置由 `quant-intel-deploy` 维护。
