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

## 跨仓配置

研究仓和数据仓通过明确的路径与公开 CLI 配置。平台不会导入相邻仓库的源码，也不会根据开发者的 home 目录猜测路径。

生产环境专用配置统一维护在 `quant-intel-deploy`。
