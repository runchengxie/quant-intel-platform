# 工作流

## Public 工作流

Public CI 运行边界检查、Ruff、类型检查、离线契约测试、文档构建和 Python 包构建。它不读取生产凭据，不抓取真实数据，也不发送消息。

## Private 工作流

生产调度、真实数据刷新、投递、回执保存和部署验证由 `quant-intel-deploy` 负责。
