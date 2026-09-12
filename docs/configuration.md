# 配置说明

配置分为两部分：仓库内的公开默认值，以及部署环境提供的运行参数。

## 公开安全的环境变量

```bash
MARKET_INTEL_CLIENT_CHAT_ID=example_client_target
MARKET_INTEL_INTERNAL_CHAT_ID=example_internal_target
MARKET_INTEL_PUBLIC_CHAT_ID=example_public_target
DATA_PLATFORM_ROOT=/path/to/local/data
```

上面的受众 ID 只是示例。目标为空时，系统仍可执行离线渲染和 CI 测试，也不会发送消息。

## 凭据

凭据应通过环境变量、本地且已被 Git 忽略的配置文件，或对应服务商要求的凭据机制提供。

请勿提交真实凭据、本地 `.env` 文件或服务商返回的真实数据快照。

## AI 市场资讯模型

AI 市场资讯支持智谱 GLM、阿里百炼和 Google Gemini。`api_keys.json` 中的
`ai_news` 配置可以提供默认值，但部署环境中的 provider-specific 环境变量会覆盖
同名字段。例如，`AI_NEWS_PROVIDER=aliyun` 与 `ALIYUN_MODEL=qwen3.7-flash` 会让
运行时使用阿里百炼的 `qwen3.7-flash`，即使 JSON 中仍有通用的 `model` 字段。

每次调用入口都会发出一条 `ai_news_runtime` 结构化日志，包含最终解析的
`provider`、`model`、`base_url` 和 `fallback_order`。该日志不包含 API key，适合用于
核对生产实际模型和服务商配置。

## 跨仓配置

研究仓和数据仓通过明确的路径与公开 CLI 配置。平台不会导入相邻仓库的源码，也不会根据开发者的 home 目录猜测路径。

生产环境专用配置统一维护在 `quant-intel-deploy`。
