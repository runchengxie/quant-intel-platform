# quant-intel-platform（Market Intel）

[在线文档](https://runchengxie.github.io/quant-intel-platform/)

`quant-intel-platform` 为市场研究提供自动化报告、网页看板和信息投递。它汇总市场与新闻信息，读取其他项目发布的版本化研究结果，再负责校验、整理、展示和投递。

本项目属于 Quant Research 项目系列，与同系列的数据平台、研究项目和生产部署项目各自独立维护、按接口协作。策略研究和回测由各自的 owner 项目负责，本项目不复制这些实现。

## 快速开始

需要 Python 3.11 至 3.13，以及 `uv`。安装项目依赖后，先查看可用命令：

```bash
uv sync --locked --no-dev
uv run dm --help
```

从[入门指南](docs/getting-started.md)了解本地报告流程。全球市场报告可以独立试用。需要 A 股正式研究产物、数据湖或生产调度时，还需配置对应的 owner 项目和权限，详见[跨项目边界](docs/boundary-contract.md)。

## 你可以在这里做什么

- 生成市场日报、A 股晨报晚报和风格周报
- 查看静态网页看板
- 按配置向指定受众投递报告并记录回执

## 文档

- [入门指南](docs/getting-started.md)：准备环境并运行报告
- [新机器配置](docs/new-machine-setup.md)：了解本地环境和配置
- [系统架构](docs/architecture.md)：查看报告生成和投递流程
- [运维手册](docs/operations.md)：查看运行、恢复与排障
- [文档索引](docs/index.md)：按主题查找其他技术说明

报告和分析用于市场信息整理，不构成投资建议。
